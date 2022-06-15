from pythreader import PyThread, synchronized, Primitive
from threading import Event
from tools import runCommand
import time, fnmatch, re
from logs import Logged

class FileDescriptor(object):

    def __init__(self, server, location, path, name, size):
        self.Server = server
        self.Location = location
        self.Path = path
        self.Name = name
        self.Size = size

        assert path.startswith(location)
        relpath = path[len(location):]
        while relpath and relpath[0] == "/":
            relpath = relpath[1:]
        self.Relpath = relpath              # path relative to the location root, with leading slash removed
       
    def __str__(self):
        return "%s:%s" % (self.Server, self.Path)
        
    __repr__ = __str__
    

class ScanManager(Primitive, Logged):

    def __init__(self, manager, config, held=False):
        Primitive.__init__(self)
        Logged.__init__(self, "ScanManager")
        self.ServersLocations = config.ScanServersLocations   # [ (server, location), ... ]
        self.StaggerInterval = float(config.ScanInterval)/len(self.ServersLocations)
        self.Scanners = {}                          # [(server, location) -> Scanner]
        self.Manager = manager
        self.Config = config
        self.Held = held
        
    @synchronized
    def start(self):
        nscanners = len(self.ServersLocations)
        dt = self.StaggerInterval/len(self.ServersLocations)
        for i, (server, location) in enumerate(self.ServersLocations):
            if i > 0:   time.sleep(dt)
            s = Scanner(self.Manager, server, location, self.Config)
            self.Scanners[(server, location)] = s
            if self.Held:   s.hold()
            s.start()
            
    @synchronized
    def hold(self):
        self.Held = True
        for s in self.Scanners.values():
            s.hold()
        
    @synchronized
    def release(self):
        self.Held = False
        for s in self.Scanners.values():
            s.release()
        
    @synchronized
    def needScan(self):
        for s in self.Scanners.values():
            s.needScan()
            
    @synchronized
    def listFiles(self, timeout):
        out = [
                (server, location) + scanner.listFiles(timeout) 
                    for (server, location), scanner in self.Scanners.items()
        ]
        return sorted(out)            

class Scanner(PyThread, Logged):

    PrescaleMultiplier = 10000

    def __init__(self, manager, server, location, config):
        PyThread.__init__(self)
        my_id = ("%x" % (id(self),))[-4:]
        Logged.__init__(self, f"Scanner@{my_id}")
        self.Manager = manager
        self.Server, self.Location = server, location
        self.FilenamePatterns = config.FilenamePatterns
        self.lsCommandTemplate = config.lsCommandTemplate\
            .replace("$server", self.Server)
                
        self.ScanInterval = config.ScanInterval
        self.DirectoryRE = re.compile(config.DirectoryRE) if config.DirectoryRE else None
        self.ParseRE = re.compile(config.ParseRE)
        self.FileRE = re.compile(config.FileRE)
        self.PathRE = re.compile(config.PathRE)
        self.SizeRE = re.compile(config.SizeRE)
        self.Recursive = config.ScanRecursive
        self.PrescaleFactor = int(config.ScanPrescale*self.PrescaleMultiplier)     # 100 means send all files
        self.PrescaleSalt = config.PrescaleSalt
        self.OperationTimeout = config.ScannerOperationTimeout
        
        self.Held = False
        self.debug("initiated")
                
    def passesPrescale(self, fn):
        return (hash(fn + self.PrescaleSalt) % self.PrescaleMultiplier) < self.PrescaleFactor
        
    @synchronized
    def scan(self):
        status, error, file_descs = self.listFilesUnder(self.Location)
        self.log("scan status:", status, "  error:", error or "-", "  files:", len(file_descs))
        if status == 0:
            data_files = {}     # fn -> desc
            # 1. scan for data files
            for desc in file_descs:
                fn = desc.Name
                #fn = path.rsplit("/", 1)[-1]
                #print("fn:", desc.Name, "  match:", any(fnmatch.fnmatch(fn, pattern) for pattern in self.FilenamePatterns),
                #              "  new:", self.Manager.newFile(fn))
                if any(fnmatch.fnmatch(fn, pattern) for pattern in self.FilenamePatterns) \
                                and self.Manager.newFile(fn):
                    if self.passesPrescale(fn):
                        data_files[fn] = desc
                    else:
                        self.debug("File rejected by prescaling: %s" % (fn,))
            self.debug("scanner: data_files:" + str(data_files))
            # 2. scan for metadata files
            for desc in file_descs:
                fn = desc.Name
                if fn.endswith(".json"):
                    data_fn = fn[:-5]
                    if data_fn in data_files:
                        desc = data_files[data_fn]
                        self.Manager.addFile(desc)
                        self.debug("File is ready: %s" % (desc,))

    def listFilesUnder(self, location):
        out = []
        status, error, files, dirs = self.listFilesAndDirs(location, self.OperationTimeout)
        #self.debug("Files: %s" % (files,))
        #self.debug("Dirs: %s" % (dirs,))
        if status == 0:
            out += files
            if self.Recursive:
                for path in dirs:
                    st, err, files = self.listFilesUnder(path)
                    if st == 0:
                        out += files
        return status, error, out


    def listFilesAndDirs(self, location, timeout):
        lscommand = self.lsCommandTemplate.replace("$location", location).replace("$server", self.Server)
        files = []
        dirs = []
        error = ""
        status, out = runCommand(lscommand, timeout, self.debug)
        if status:
            error = out
            self.log("Error in ls (%s): %s" % (lscommand, error,))
        else:
            lines = [x.strip() for x in out.split("\n")]
            for l in lines:
                l = l.strip()
                if l:
                    m = self.ParseRE.match(l)
                    if m:
                        t = m["type"]
                        path = m["path"]
                        if t in "f-":
                            size = int(m["size"])
                            name = path.rsplit("/",1)[-1]
                            path = path if path.startswith(location) else location + "/" + path
                            files.append(FileDescriptor(self.Server, location, path, name, size))
                        elif t == "d": 
                            path = path if path.startswith(location) else location + "/" + path
                            dirs.append(path)
                        else:
                            print(f"Unknown directory entry type '{t}' in: {l} -- ignored")
                    else:
                        print("can not parse ls line:", l)
        return status, error, files, dirs
        
    @synchronized
    def listFiles(self, timeout):
        status, error, files = self.listFilesUnder(self.Location)
        return status, error, files

    def needScan(self):
        self.wakeup()

    def hold(self):
        self.log("held")
        self.Held = True
        
    def release(self):
        self.log("released")
        self.Held = False
        self.wakeup()

    def run(self):
        while True:
            if not self.Held:
                self.scan()
            self.debug("waiting...")
            self.sleep(self.ScanInterval)
