APPNAME = server-core
DEPS =
VIRTUALENV = virtualenv
PYTHON = bin/python
NOSE = bin/nosetests -s --with-xunit
FLAKE8 = bin/flake8
COVEROPTS = --cover-html --cover-html-dir=html --with-coverage --cover-package=services
TESTS = services
PKGS = services
COVERAGE = bin/coverage
PYLINT = bin/pylint
SERVER = dev-auth.services.mozilla.com
SCHEME = https
BUILDAPP = bin/buildapp
BUILDRPMS = bin/buildrpms
PYPI = http://pypi.python.org/simple
PYPI2RPM = bin/pypi2rpm.py --index=$(PYPI)
PYPIOPTIONS = -i $(PYPI)
CHANNEL = prod
INSTALL = bin/pip install
INSTALLOPTIONS = -U -i $(PYPI)

ifdef PYPIEXTRAS
	PYPIOPTIONS += -e $(PYPIEXTRAS)
	INSTALLOPTIONS += -f $(PYPIEXTRAS)
endif

ifdef PYPISTRICT
	PYPIOPTIONS += -s
	ifdef PYPIEXTRAS
		HOST = `python -c "import urlparse; print urlparse.urlparse('$(PYPI)')[1] + ',' + urlparse.urlparse('$(PYPIEXTRAS)')[1]"`

	else
		HOST = `python -c "import urlparse; print urlparse.urlparse('$(PYPI)')[1]"`
	endif
	INSTALLOPTIONS += --install-option="--allow-hosts=$(HOST)"

endif

INSTALL += $(INSTALLOPTIONS)

.PHONY: all build build_extras build_rpms test

all:	build

build:
	$(VIRTUALENV) --no-site-packages --distribute .
	$(INSTALL) MoPyTools
	$(INSTALL) -r $(CHANNEL)-reqs.txt
	$(BUILDAPP) $(PYPIOPTIONS) $(APPNAME) $(DEPS)
	$(INSTALL) nose
	$(INSTALL) WebTest

build_extras:
	$(INSTALL) MySQL-python
	$(INSTALL) recaptcha-client
	$(INSTALL) wsgiproxy
	$(INSTALL) wsgi_intercept
	$(INSTALL) "python-ldap == 2.3.13"
	$(INSTALL) coverage
	$(INSTALL) Pygments

test:
	$(NOSE) $(TESTS)

coverage:
	rm -rf html
	- $(NOSE) $(COVEROPTS) $(TESTS)

build_rpms:
	$(INSTALL) pypi2rpm
	rm -rf $(CURDIR)/rpms
	mkdir $(CURDIR)/rpms
	rm -rf build; $(PYTHON) setup.py --command-packages=pypi2rpm.command bdist_rpm2 --spec-file=Services.spec --dist-dir=$(CURDIR)/rpms
	$(BUILDRPMS) $(CHANNEL)-reqs.txt --dist-dir=$(CURDIR)/rpms
