from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'Ask Shubham Retrieval Service'
    knowledge_dir: str = '../data/knowledge'
    embedding_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    default_top_k: int = 5
    cors_origins: str = 'http://localhost:3000,https://shubham-pareek-portfolio.vercel.app'
    database_url: str | None = None
    sports_database_url: str = 'postgresql://creatorhub:creatorhub_pass@localhost:5433/creatorhub_dev'
    sports_knowledge_dir: str = './data/sports_analytics'
    sports_default_limit: int = 10
    sports_retrieval_top_k: int = 4
    sports_auto_bootstrap: bool = False
    sports_schema_sql_path: str = './sql/sports_analytics_schema.sql'
    sports_seed_sql_path: str = './sql/sports_analytics_seed.sql'


settings = Settings()
