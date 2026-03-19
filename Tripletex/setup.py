from setuptools import find_packages, setup


setup(
    name="tripletex-agent",
    version="0.1.0",
    description="Self-contained Tripletex competition agent.",
    python_requires=">=3.8",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.115,<1.0",
        "httpx>=0.28,<0.29",
        "pydantic>=2.9,<3.0",
        "pydantic-settings>=2.6,<3.0",
        "uvicorn>=0.34,<0.35",
    ],
    extras_require={"dev": ["pytest>=8.3,<9.0"]},
)
