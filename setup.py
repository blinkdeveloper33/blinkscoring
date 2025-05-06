from setuptools import setup, find_packages

setup(
    name="blinkscoring-ml",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.105.0",
        "uvicorn>=0.24.0",
        "sqlalchemy>=2.0.23",
        "psycopg2-binary>=2.9.9",
        "python-dotenv>=1.0.0",
        "structlog>=23.2.0",
        "pandas>=2.1.3",
        "numpy>=1.26.2",
    ],
    python_requires=">=3.9",
) 