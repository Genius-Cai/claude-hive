#!/usr/bin/env python3
"""
Claude-Hive: Distributed Claude Code Orchestration Framework

Installation:
    pip install -e .

Or install from PyPI (when published):
    pip install claude-hive
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = ""
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")

setup(
    name="claude-hive",
    version="0.2.0",
    author="Genius-Cai",
    author_email="",
    description="Distributed Claude Code orchestration framework for LAN environments",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Genius-Cai/claude-hive",
    project_urls={
        "Bug Tracker": "https://github.com/Genius-Cai/claude-hive/issues",
        "Documentation": "https://github.com/Genius-Cai/claude-hive#readme",
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Distributed Computing",
    ],
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "click>=8.1.0",
        "httpx>=0.25.0",
        "pyyaml>=6.0.0",
        "pydantic>=2.5.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "black>=23.0.0",
            "ruff>=0.1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "hive=hive.cli:main",
            "hive-worker=worker.server:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
