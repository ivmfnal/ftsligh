VERSION = 3.6
PRODUCT = FTS-light3
BUILD_HOME = $(HOME)/build
BUILD_DIR = $(BUILD_HOME)/$(PRODUCT)
TAR_DIR = /tmp/$(USER)
TAR_FILE = $(TAR_DIR)/$(PRODUCT)_$(VERSION).tar


FILES = \
	charts.html	      GUI.py	     index.html      template.html  Version.py  \
	config.html	      history.html   input_dir.html  log.html	 Mover.py       Scanner.py     tools.py	 \
	GraphiteInterface.py  mover.cfg	static	      WebService.py  \
	logs.py uid.py fts3client


all: tarball

tarball: build $(TAR_DIR)
	cd $(BUILD_DIR); tar cf $(TAR_FILE) *
	@echo
	@echo Tar file $(TAR_FILE) is ready
	@echo
	
build: $(BUILD_DIR)
	find . -type f -name \*.pyc -exec rm -f {} \;
	cp -R $(FILES) $(BUILD_DIR)
	cp -R run $(BUILD_DIR)
	echo 'Version="$(VERSION)"' > $(BUILD_DIR)/Version.py
	
clean:
	rm -rf $(TAR_FILE) $(BUILD_DIR)

$(BUILD_DIR):
	mkdir -p $@

$(TAR_DIR):
	mkdir -p $@



