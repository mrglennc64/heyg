from setuptools import find_packages, setup

setup(
    name="forge-shared",
    version="0.1.0",
    packages=find_packages(),
    install_requires=["pydantic>=2", "pydantic-settings>=2", "celery[redis]>=5.4", "boto3"],
)
