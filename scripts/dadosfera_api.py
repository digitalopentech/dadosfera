"""
Dadosfera API Client — Utilitario Python

Wrapper para a API REST da Dadosfera (Maestro), com autenticacao,
gerenciamento de catalogo, refresh automatico de token e retry logic.

Uso:
    from dadosfera_api import DadosferaClient

    client = DadosferaClient.from_env()
    assets = client.list_catalog_assets()
    dashboards = client.get_assets_by_type("dashboard")

Variaveis de ambiente necessarias (.env):
    DADOSFERA_USERNAME=seu_email@exemplo.com
    DADOSFERA_PASSWORD=sua_senha
    DADOSFERA_MAESTRO_URL=https://maestro.dadosfera.ai  (opcional)
"""

import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("dadosfera_api")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DadosferaError(Exception):
    """Erro base para operacoes da API Dadosfera."""


class AuthenticationError(DadosferaError):
    """Falha na autenticacao com a API."""


class RateLimitError(DadosferaError):
    """Rate limit atingido na API."""


class AssetNotFoundError(DadosferaError):
    """Asset nao encontrado no catalogo."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class DadosferaClient:
    """
    Cliente para a API REST da Dadosfera (Maestro).

    Funcionalidades:
    - Autenticacao com refresh automatico de token
    - CRUD de assets no catalogo de dados
    - Filtragem por tipo de asset
    - Retry com backoff exponencial
    - Logging estruturado

    Attributes:
        username: Email do usuario Dadosfera.
        password: Senha do usuario.
        maestro_url: URL base da API Maestro.
        token: Token de acesso atual (preenchido apos autenticacao).
        token_expires_at: Datetime de expiracao do token.
    """

    DEFAULT_MAESTRO_URL = "https://maestro.dadosfera.ai"
    TOKEN_LIFETIME_HOURS = 8  # Estimativa conservadora de vida do token

    def __init__(
        self,
        username: str,
        password: str,
        maestro_url: str = DEFAULT_MAESTRO_URL,
    ) -> None:
        """
        Inicializa o cliente Dadosfera.

        Args:
            username: Email do usuario.
            password: Senha do usuario.
            maestro_url: URL base da API Maestro.

        Raises:
            ValueError: Se username ou password estiverem vazios.
        """
        if not username or not password:
            raise ValueError(
                "Username e password sao obrigatorios. "
                "Configure DADOSFERA_USERNAME e DADOSFERA_PASSWORD no .env."
            )

        self.username = username
        self.password = password
        self.maestro_url = maestro_url.rstrip("/")
        self.token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None

        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

        logger.info(
            "DadosferaClient inicializado | URL: %s | User: %s",
            self.maestro_url,
            self.username,
        )

    @classmethod
    def from_env(cls) -> "DadosferaClient":
        """
        Cria um DadosferaClient a partir de variaveis de ambiente.

        Variaveis esperadas:
            DADOSFERA_USERNAME
            DADOSFERA_PASSWORD
            DADOSFERA_MAESTRO_URL (opcional)

        Returns:
            Instancia configurada do DadosferaClient.

        Raises:
            ValueError: Se variaveis obrigatorias nao estiverem definidas.
        """
        username = os.getenv("DADOSFERA_USERNAME", "")
        password = os.getenv("DADOSFERA_PASSWORD", "")
        maestro_url = os.getenv("DADOSFERA_MAESTRO_URL", cls.DEFAULT_MAESTRO_URL)

        return cls(
            username=username,
            password=password,
            maestro_url=maestro_url,
        )

    # ------------------------------------------------------------------
    # Autenticacao
    # ------------------------------------------------------------------

    def authenticate(self) -> str:
        """
        Autentica com a API Dadosfera e retorna o access token.

        Endpoint: POST /auth/sign-in

        Returns:
            Token de acesso (string).

        Raises:
            AuthenticationError: Se a autenticacao falhar.
        """
        url = f"{self.maestro_url}/auth/sign-in"
        payload = {
            "username": self.username,
            "password": self.password,
        }

        logger.info("Autenticando com Dadosfera API...")

        try:
            response = self._session.post(url, json=payload, timeout=30)
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response else 0
            if status == 401:
                raise AuthenticationError(
                    "Credenciais invalidas. Verifique DADOSFERA_USERNAME "
                    "e DADOSFERA_PASSWORD."
                ) from exc
            if status == 403:
                raise AuthenticationError(
                    "Acesso negado. Verifique se o usuario tem permissao "
                    "para acessar a API."
                ) from exc
            raise AuthenticationError(
                f"Erro HTTP {status} na autenticacao: {exc}"
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise AuthenticationError(
                f"Nao foi possivel conectar a {url}. "
                "Verifique a URL e sua conexao de rede."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise AuthenticationError(
                "Timeout na autenticacao. Tente novamente."
            ) from exc

        data = response.json()
        self.token = data.get("accessToken") or data.get("access_token")

        if not self.token:
            raise AuthenticationError(
                "Resposta da API nao contem 'accessToken'. "
                f"Campos recebidos: {list(data.keys())}"
            )

        self.token_expires_at = datetime.now() + timedelta(
            hours=self.TOKEN_LIFETIME_HOURS
        )
        self._session.headers["Authorization"] = f"Bearer {self.token}"

        logger.info(
            "Autenticacao bem-sucedida | Token expira em: %s",
            self.token_expires_at.isoformat(),
        )

        return self.token

    def _ensure_authenticated(self) -> None:
        """Garante que existe um token valido, renovando se necessario."""
        if self.token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return

        if self.token:
            logger.info("Token expirado. Renovando autenticacao...")
        self.authenticate()

    # ------------------------------------------------------------------
    # Request helper com retry
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        endpoint: str,
        retries: int = 3,
        backoff_base: float = 2.0,
        **kwargs: Any,
    ) -> requests.Response:
        """
        Executa uma requisicao HTTP com retry e backoff exponencial.

        Args:
            method: Metodo HTTP (GET, POST, PUT, DELETE).
            endpoint: Endpoint relativo (ex: /catalog).
            retries: Numero de tentativas.
            backoff_base: Base para backoff exponencial.
            **kwargs: Argumentos adicionais para requests.

        Returns:
            Objeto Response.

        Raises:
            DadosferaError: Se todas as tentativas falharem.
            RateLimitError: Se o rate limit for atingido repetidamente.
        """
        self._ensure_authenticated()

        url = f"{self.maestro_url}{endpoint}"
        kwargs.setdefault("timeout", 30)

        last_error: Optional[Exception] = None

        for attempt in range(retries):
            try:
                response = self._session.request(method, url, **kwargs)

                if response.status_code == 401:
                    logger.warning("Token invalido. Re-autenticando...")
                    self.authenticate()
                    response = self._session.request(method, url, **kwargs)

                if response.status_code == 429:
                    wait = backoff_base ** (attempt + 1)
                    logger.warning(
                        "Rate limit (429). Aguardando %.0fs (tentativa %d/%d)",
                        wait, attempt + 1, retries,
                    )
                    time.sleep(wait)
                    continue

                response.raise_for_status()
                return response

            except requests.exceptions.HTTPError as exc:
                last_error = exc
                status = exc.response.status_code if exc.response else 0

                if status >= 500:
                    wait = backoff_base ** attempt
                    logger.warning(
                        "Erro servidor (%d). Aguardando %.0fs (tentativa %d/%d)",
                        status, wait, attempt + 1, retries,
                    )
                    time.sleep(wait)
                    continue

                raise DadosferaError(
                    f"Erro HTTP {status} em {method} {endpoint}: {exc}"
                ) from exc

            except requests.exceptions.ConnectionError as exc:
                last_error = exc
                wait = backoff_base ** attempt
                logger.warning(
                    "Erro de conexao. Aguardando %.0fs (tentativa %d/%d)",
                    wait, attempt + 1, retries,
                )
                time.sleep(wait)

            except requests.exceptions.Timeout as exc:
                last_error = exc
                wait = backoff_base ** attempt
                logger.warning(
                    "Timeout. Aguardando %.0fs (tentativa %d/%d)",
                    wait, attempt + 1, retries,
                )
                time.sleep(wait)

        raise DadosferaError(
            f"Todas as {retries} tentativas falharam para "
            f"{method} {endpoint}. Ultimo erro: {last_error}"
        )

    # ------------------------------------------------------------------
    # Catalogo de dados
    # ------------------------------------------------------------------

    def list_catalog_assets(
        self,
        page: int = 1,
        size: int = 100,
    ) -> list[dict]:
        """
        Lista assets do catalogo de dados.

        Endpoint: GET /catalog

        Args:
            page: Numero da pagina (1-indexed).
            size: Quantidade de assets por pagina (max 100).

        Returns:
            Lista de dicionarios representando data assets.
        """
        logger.info("Listando assets do catalogo (page=%d, size=%d)", page, size)

        response = self._request(
            "GET",
            "/catalog",
            params={"page": page, "size": min(size, 100)},
        )

        data = response.json()

        # A API pode retornar em diferentes formatos
        if isinstance(data, list):
            assets = data
        elif isinstance(data, dict):
            assets = (
                data.get("data_assets")
                or data.get("dataAssets")
                or data.get("data")
                or data.get("items")
                or data.get("results")
                or []
            )
        else:
            assets = []

        logger.info("Encontrados %d assets na pagina %d", len(assets), page)
        return assets

    def list_all_catalog_assets(self, page_size: int = 100) -> list[dict]:
        """
        Lista todos os assets do catalogo, percorrendo todas as paginas.

        Args:
            page_size: Tamanho de cada pagina.

        Returns:
            Lista completa de todos os data assets.
        """
        all_assets: list[dict] = []
        page = 1

        while True:
            assets = self.list_catalog_assets(page=page, size=page_size)
            if not assets:
                break
            all_assets.extend(assets)
            if len(assets) < page_size:
                break
            page += 1

        logger.info("Total de assets no catalogo: %d", len(all_assets))
        return all_assets

    def get_asset(self, asset_id: str) -> dict:
        """
        Busca um asset especifico por ID.

        Endpoint: GET /catalog/data-asset/{asset_id}

        Args:
            asset_id: Identificador unico do asset.

        Returns:
            Dicionario com os dados do asset.

        Raises:
            AssetNotFoundError: Se o asset nao existir.
        """
        logger.info("Buscando asset: %s", asset_id)

        try:
            response = self._request("GET", f"/catalog/data-asset/{asset_id}")
            return response.json()
        except DadosferaError as exc:
            if "404" in str(exc):
                raise AssetNotFoundError(
                    f"Asset '{asset_id}' nao encontrado no catalogo."
                ) from exc
            raise

    def update_asset(
        self,
        asset_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> dict:
        """
        Atualiza metadados de um asset no catalogo.

        Endpoint: PUT /catalog/data-asset/{asset_id}

        Args:
            asset_id: Identificador unico do asset.
            name: Novo nome do asset (opcional).
            description: Nova descricao (opcional).
            tags: Lista de tags (opcional).

        Returns:
            Dicionario com os dados atualizados do asset.

        Raises:
            AssetNotFoundError: Se o asset nao existir.
            ValueError: Se nenhum campo para atualizar for fornecido.
        """
        payload: dict[str, Any] = {}

        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if tags is not None:
            payload["tags"] = tags

        if not payload:
            raise ValueError(
                "Pelo menos um campo (name, description ou tags) "
                "deve ser fornecido para atualizacao."
            )

        logger.info(
            "Atualizando asset %s | Campos: %s",
            asset_id,
            list(payload.keys()),
        )

        try:
            response = self._request(
                "PUT",
                f"/catalog/data-asset/{asset_id}",
                json=payload,
            )
            logger.info("Asset %s atualizado com sucesso.", asset_id)
            return response.json()
        except DadosferaError as exc:
            if "404" in str(exc):
                raise AssetNotFoundError(
                    f"Asset '{asset_id}' nao encontrado para atualizacao."
                ) from exc
            raise

    def get_assets_by_type(self, asset_type: str) -> list[dict]:
        """
        Filtra assets do catalogo por tipo.

        Tipos comuns: dashboard, dataset, table, view, report, notebook.

        Args:
            asset_type: Tipo de asset para filtrar (case-insensitive).

        Returns:
            Lista de assets que correspondem ao tipo.
        """
        logger.info("Filtrando assets por tipo: %s", asset_type)

        all_assets = self.list_all_catalog_assets()

        asset_type_lower = asset_type.lower()
        filtered = [
            asset
            for asset in all_assets
            if (
                asset.get("type", "").lower() == asset_type_lower
                or asset.get("asset_type", "").lower() == asset_type_lower
                or asset.get("assetType", "").lower() == asset_type_lower
            )
        ]

        logger.info(
            "Encontrados %d assets do tipo '%s' (de %d total)",
            len(filtered),
            asset_type,
            len(all_assets),
        )

        return filtered

    def search_assets(self, query: str) -> list[dict]:
        """
        Busca assets por texto livre (nome, descricao ou tags).

        Args:
            query: Texto de busca (case-insensitive).

        Returns:
            Lista de assets que correspondem a busca.
        """
        logger.info("Buscando assets com query: '%s'", query)

        all_assets = self.list_all_catalog_assets()
        query_lower = query.lower()

        results = []
        for asset in all_assets:
            name = asset.get("name", "").lower()
            description = asset.get("description", "").lower()
            tags = [t.lower() for t in asset.get("tags", [])]

            if (
                query_lower in name
                or query_lower in description
                or any(query_lower in tag for tag in tags)
            ):
                results.append(asset)

        logger.info("Busca retornou %d resultados", len(results))
        return results

    def get_catalog_summary(self) -> dict[str, int]:
        """
        Retorna um resumo do catalogo agrupado por tipo de asset.

        Returns:
            Dicionario {tipo: contagem}.
        """
        all_assets = self.list_all_catalog_assets()
        summary: dict[str, int] = {}

        for asset in all_assets:
            asset_type = (
                asset.get("type")
                or asset.get("asset_type")
                or asset.get("assetType")
                or "unknown"
            )
            summary[asset_type] = summary.get(asset_type, 0) + 1

        logger.info("Resumo do catalogo: %s", summary)
        return summary

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def bulk_update_tags(
        self,
        asset_ids: list[str],
        tags: list[str],
        append: bool = True,
    ) -> list[dict]:
        """
        Atualiza tags de multiplos assets em lote.

        Args:
            asset_ids: Lista de IDs de assets.
            tags: Tags a serem aplicadas.
            append: Se True, adiciona as tags existentes. Se False, substitui.

        Returns:
            Lista de resultados (sucesso/erro por asset).
        """
        logger.info(
            "Atualizando tags de %d assets | Tags: %s | Append: %s",
            len(asset_ids),
            tags,
            append,
        )

        results = []
        for asset_id in asset_ids:
            try:
                if append:
                    current = self.get_asset(asset_id)
                    existing_tags = current.get("tags", [])
                    merged_tags = list(set(existing_tags + tags))
                    result = self.update_asset(asset_id, tags=merged_tags)
                else:
                    result = self.update_asset(asset_id, tags=tags)

                results.append({
                    "asset_id": asset_id,
                    "status": "success",
                    "data": result,
                })
            except DadosferaError as exc:
                logger.error("Erro ao atualizar asset %s: %s", asset_id, exc)
                results.append({
                    "asset_id": asset_id,
                    "status": "error",
                    "error": str(exc),
                })

        success_count = sum(1 for r in results if r["status"] == "success")
        logger.info(
            "Bulk update concluido: %d/%d sucesso",
            success_count,
            len(asset_ids),
        )

        return results

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "DadosferaClient":
        self.authenticate()
        return self

    def __exit__(self, *args: Any) -> None:
        self._session.close()

    def __repr__(self) -> str:
        auth_status = "authenticated" if self.token else "not authenticated"
        return (
            f"DadosferaClient(url='{self.maestro_url}', "
            f"user='{self.username}', status='{auth_status}')"
        )


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------


def get_client() -> DadosferaClient:
    """
    Factory function que cria e autentica um cliente Dadosfera.

    Returns:
        DadosferaClient autenticado e pronto para uso.
    """
    client = DadosferaClient.from_env()
    client.authenticate()
    return client


# ---------------------------------------------------------------------------
# CLI usage
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("Dadosfera API Client — Test de Conectividade")
    print("=" * 50)

    try:
        client = get_client()
        print(f"  Autenticacao: OK")
        print(f"  Token expira: {client.token_expires_at}")

        print("\nListando assets do catalogo...")
        assets = client.list_catalog_assets(page=1, size=10)
        print(f"  Assets encontrados (pagina 1): {len(assets)}")

        if assets:
            print("\n  Primeiros assets:")
            for asset in assets[:5]:
                name = asset.get("name", "sem nome")
                asset_type = (
                    asset.get("type")
                    or asset.get("asset_type")
                    or "unknown"
                )
                print(f"    - [{asset_type}] {name}")

        print("\nResumo do catalogo:")
        summary = client.get_catalog_summary()
        for asset_type, count in sorted(summary.items(), key=lambda x: -x[1]):
            print(f"    {asset_type}: {count}")

        print("\nTeste concluido com sucesso.")

    except AuthenticationError as exc:
        print(f"\n  ERRO de autenticacao: {exc}", file=sys.stderr)
        sys.exit(1)
    except DadosferaError as exc:
        print(f"\n  ERRO da API: {exc}", file=sys.stderr)
        sys.exit(1)
    except ValueError as exc:
        print(f"\n  ERRO de configuracao: {exc}", file=sys.stderr)
        print(
            "  Verifique se DADOSFERA_USERNAME e DADOSFERA_PASSWORD "
            "estao configurados no .env.",
            file=sys.stderr,
        )
        sys.exit(1)
