"""
Tests of the project generation output.
"""

import logging
import logging.config
import os
import re
from pathlib import Path
from contextlib import contextmanager

import pytest
import sh


LOGGING_CONFIG = {
    'version': 1,
    'incremental': True,
    'loggers': {
        'binaryornot': {
            'level': logging.INFO,
        },
        'sh': {
            'level': logging.INFO,
        }
    }
}
logging.config.dictConfig(LOGGING_CONFIG)


@contextmanager
def inside_dir(dirpath):
    """
    Change into a directory and change back at the end of the with-statement.

    Args:
        dirpath (str): the path of the directory to change into.

    """
    old_path = os.getcwd()
    try:
        os.chdir(dirpath)
        yield
    finally:
        os.chdir(old_path)


@contextmanager
def bake_in_temp_dir(cookies, *args, **kwargs):
    """
    Bake a cookiecutter, and switch into the resulting directory.

    Args:
        cookies (pytest_cookies.Cookies): the cookie to be baked.

    """
    result = cookies.bake(*args, **kwargs)
    if result.exception:
        raise result.exception
    with inside_dir(str(result.project)):
        yield




common = {
    "app_name": "cookie_lover",
    "repo_name": "cookie_repo",
}

configurations = [
    pytest.param(
        {
            **common,
        },
        id="no models"
    ),
    pytest.param(
        {
            **common,
            "models": "ChocolateChip,Zimsterne",
        },
        id="two models"
    ),
]


@pytest.fixture(name='custom_template')
def fixture_custom_template(cookies_session):
    template = cookies_session._default_template + "/cookiecutter-django-app"
    return template

@pytest.fixture(params=configurations, name='options_baked')
def fixture_options_baked(cookies_session, request, custom_template):
    """
    Bake a cookie cutter, parameterized by configurations.

    Provides the configuration dict, and changes into the directory with the
    baked result.
    """
    with bake_in_temp_dir(cookies_session, extra_context=request.param, template=custom_template):
        yield request.param


# Fixture names aren't always used in test functions. Disable completely.
# pylint: disable=unused-argument

@pytest.mark.parametrize("license_name, target_string", [
    ('AGPL 3.0', 'GNU AFFERO GENERAL PUBLIC LICENSE'),
    ('Apache Software License 2.0', 'Apache'),
])
def test_bake_selecting_license(cookies, license_name, target_string, custom_template):
    """Test to check if LICENSE.txt gets the correct license selected."""
    with bake_in_temp_dir(cookies, extra_context={'open_source_license': license_name}, template=custom_template):
        assert target_string in Path("LICENSE.txt").read_text()
        assert license_name in Path("setup.py").read_text()


def test_readme(options_baked, custom_template):
    """The generated README.rst file should pass some sanity checks and validate as a PyPI long description."""
    readme_file = Path('README.rst')
    readme_lines = [x.strip() for x in readme_file.open()]
    assert "cookie_repo" == readme_lines[0]
    assert 'The full documentation is at https://cookie_repo.readthedocs.org.' in readme_lines
    try:
        sh.python("setup.py", 'check', restructuredtext=True, strict=True)
    except sh.ErrorReturnCode as exc:
        pytest.fail(str(exc))


def test_models(options_baked):
    """The generated models.py file should pass a sanity check."""
    if "models" not in options_baked:
        pytest.skip("No models to check")
    model_txt = Path("cookie_lover/models.py").read_text()
    for model_name in options_baked.get("models").split(","):
        pattern = r'^class {}\(TimeStampedModel\):$'.format(model_name)
        assert re.search(pattern, model_txt, re.MULTILINE)


def test_urls(options_baked):
    """The urls.py file should be present."""
    urls_file_txt = Path("cookie_lover/urls.py").read_text()
    basic_url = "url(r'', TemplateView.as_view(template_name=\"cookie_lover/base.html\"))"
    assert basic_url in urls_file_txt


def test_travis(options_baked):
    """The generated .travis.yml file should pass a sanity check."""
    travis_text = Path(".travis.yml").read_text()
    assert 'pip install -r requirements/travis.txt' in travis_text


def test_app_config(options_baked):
    """The generated Django AppConfig should look correct."""
    init_text = Path("cookie_lover/__init__.py").read_text()
    pattern = r"^default_app_config = 'cookie_lover.apps.CookieLoverConfig'  #"
    assert re.search(pattern, init_text, re.MULTILINE)

    apps_text = Path("cookie_lover/apps.py").read_text()
    pattern = r'^class CookieLoverConfig\(AppConfig\):$'
    assert re.search(pattern, apps_text, re.MULTILINE)


def test_manifest(options_baked):
    """The generated MANIFEST.in should pass a sanity check."""
    manifest_text = Path("MANIFEST.in").read_text()
    assert 'recursive-include cookie_lover *.html' in manifest_text


def test_setup_py(options_baked):
    """The generated setup.py should pass a sanity check."""
    setup_text = Path("setup.py").read_text()
    assert "VERSION = get_version('cookie_lover', '__init__.py')" in setup_text
    assert "    author='edX'," in setup_text


def test_quality(options_baked):
    """Run quality tests on the given generated output."""
    for dirpath, _dirnames, filenames in os.walk("."):
        for filename in filenames:
            name = os.path.join(dirpath, filename)
            if not name.endswith('.py'):
                continue
            try:
                sh.pylint(name)
                sh.pycodestyle(name)
                sh.pydocstyle(name)
                sh.isort(name, check_only=True, diff=True)
            except sh.ErrorReturnCode as exc:
                pytest.fail(str(exc))

    try:
        # Sanity check the generated Makefile
        sh.make('help')
        # quality check docs
        sh.doc8("README.rst", ignore_path="docs/_build")
        sh.doc8("docs", ignore_path="docs/_build")
    except sh.ErrorReturnCode as exc:
        pytest.fail(str(exc))


# def test_pii_annotations(options_baked):
#     """
#     Test that the pii_check make target works correctly.
#     """
#     try:
#         sh.make('pii_check')
#     except sh.ErrorReturnCode as exc:
#         # uncovered models are expected IFF we generated any models via the cookiecutter.
#         expected_uncovered_models = 0
#         if 'models' in options_baked:
#             # count the number of (unannotated) models the cookiecutter should generate.
#             expected_uncovered_models = len(options_baked['models'].split(','))
#         expected_message = 'Coverage found {} uncovered models:'.format(expected_uncovered_models)
#         if expected_message not in str(exc.stdout):
#             # First, print the stdout/stderr attrs, otherwise sh will truncate the output
#             # guaranteeing that all we see is useless tox setup.
#             print(exc.stdout)
#             print(exc.stderr)
#             pytest.fail(str(exc))
