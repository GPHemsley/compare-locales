# ***** BEGIN LICENSE BLOCK *****
# Version: MPL 1.1/GPL 2.0/LGPL 2.1
#
# The contents of this file are subject to the Mozilla Public License Version
# 1.1 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
# http://www.mozilla.org/MPL/
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License
# for the specific language governing rights and limitations under the
# License.
#
# The Original Code is l10n test automation.
#
# The Initial Developer of the Original Code is
# Mozilla Foundation
# Portions created by the Initial Developer are Copyright (C) 2006
# the Initial Developer. All Rights Reserved.
#
# Contributor(s):
#	Axel Hecht <l10n@mozilla.com>
#
# Alternatively, the contents of this file may be used under the terms of
# either the GNU General Public License Version 2 or later (the "GPL"), or
# the GNU Lesser General Public License Version 2.1 or later (the "LGPL"),
# in which case the provisions of the GPL or the LGPL are applicable instead
# of those above. If you wish to allow use of your version of this file only
# under the terms of either the GPL or the LGPL, and not to allow others to
# use your version of this file under the terms of the MPL, indicate your
# decision by deleting the provisions above and replace them with the notice
# and other provisions required by the GPL or the LGPL. If you do not delete
# the provisions above, a recipient may use your version of this file under
# the terms of any one of the MPL, the GPL or the LGPL.
#
# ***** END LICENSE BLOCK *****

import os.path
import os
from ConfigParser import ConfigParser, NoSectionError, NoOptionError
from urlparse import urlparse, urljoin
from urllib import pathname2url, url2pathname
from urllib2 import urlopen
from Mozilla.CompareLocales import defaultdict

class L10nConfigParser(object):
  '''Helper class to gather application information from ini files.

  This class is working on synchronous open to read files or web data.
  Subclass this and overwrite loadConfigs and addChild if you need async.
  '''
  def __init__(self, inipath, **kwargs):
    """Constructor for L10nConfigParsers
    
    inipath -- l10n.ini path
    Optional keyword arguments are fowarded to the inner ConfigParser as
    defaults.
    """
    if os.path.isabs(inipath):
      self.inipath = 'file:%s' % pathname2url(inipath)
    else:
      pwdurl = 'file:%s/' % pathname2url(os.getcwd())
      self.inipath = urljoin(pwdurl, inipath)
    # l10n.ini files can import other l10n.ini files, store the 
    # corresponding L10nConfigParsers
    self.children = []
    # we really only care about the l10n directories described in l10n.ini
    self.dirs = []
    # optional defaults to be passed to the inner ConfigParser (unused?)
    self.defaults = kwargs

  def getDepth(self, cp):
    '''Get the depth for the comparison from the parsed l10n.ini.

    Overloadable to get the source depth for fennec and friends.
    '''
    try:
      depth = cp.get('general', 'depth')
    except:
      depth = '.'
    return depth

  def getFilters(self):
    '''Get the test functions from this ConfigParser and all children.

    Only works with synchronous loads, used by compare-locales, which
    is local anyway.
    '''
    filterurl = urljoin(self.inipath, 'filter.py')
    try:
      l = {}
      execfile(url2pathname(urlparse(filterurl).path), {}, l)
      if 'test' in l and callable(l['test']):
        filters = [l['test']]
      else:
        filters = []
    except:
      filters = []

    for c in self.children:
      filters += c.getFilters()

    return filters


  def loadConfigs(self):
    """Entry point to load the l10n.ini file this Parser refers to.

    This implementation uses synchronous loads, subclasses might overload
    this behaviour. If you do, make sure to pass a file-like object
    to onLoadConfig.
    """
    self.onLoadConfig(urlopen(self.inipath))

  def onLoadConfig(self, inifile):
    """Parse a file-like object for the loaded l10n.ini file."""
    cp = ConfigParser(self.defaults)
    cp.readfp(inifile)
    depth = self.getDepth(cp)
    self.baseurl = urljoin(self.inipath, depth)
    # create child loaders for any other l10n.ini files to be included
    try:
      for title, path in cp.items('includes'):
        # skip default items
        if title in self.defaults:
          continue
        # add child config parser
        self.addChild(title, path, cp)
    except NoSectionError:
      pass
    # try to load the "dirs" defined in the "compare" section
    try:
      self.dirs.extend(cp.get('compare', 'dirs').split())
    except (NoOptionError, NoSectionError):
      pass
    # try getting a top level compare dir, as used for fennec
    try:
      self.tld = cp.get('compare', 'tld')
      # remove tld from comparison dirs
      if self.tld in self.dirs:
        self.dirs.remove(self.tld)
    except (NoOptionError, NoSectionError):
      self.tld = None
    # try to set "all_path" and "all_url"
    try:
      self.all_path = cp.get('general', 'all')
      self.all_url = urljoin(self.baseurl, self.all_path)
    except (NoOptionError, NoSectionError):
      self.all_path = None
      self.all_url = None
    return cp

  def addChild(self, title, path, orig_cp):
    """Create a child L10nConfigParser and load it.
    
    title -- indicates the module's name
    path -- indicates the path to the module's l10n.ini file
    orig_cp -- the configuration parser of this l10n.ini
    """
    cp = L10nConfigParser(urljoin(self.baseurl, path), **self.defaults)
    cp.loadConfigs()
    self.children.append(cp)

  def dirsIter(self):
    """Iterate over all dirs and our base path for this l10n.ini"""
    url = urlparse(self.baseurl)
    basepath = url2pathname(url[2])
    for dir in self.dirs:
      yield dir, (basepath, dir)
    

  def directories(self):
    """Iterate over all dirs and base paths for this l10n.ini as well
    as the included ones.
    """
    for t in self.dirsIter():
      yield t
    for child in self.children:
      for t in child.directories():
        yield t

  def allLocales(self):
    """Return a list of all the locales of this project"""
    return urlopen(self.all_url).read().splitlines()


class SourceTreeConfigParser(L10nConfigParser):
  '''Subclassing L10nConfigParser to work with just the repos
  checked out next to each other instead of intermingled like
  we do for real builds.
  '''

  def __init__(self, inipath, basepath):
    '''Add additional arguments basepath.

    basepath is used to resolve local paths via branchnames.
    '''
    L10nConfigParser.__init__(self, inipath)
    self.basepath = basepath
    self.tld = None

  def getDepth(self, cp):
    '''Get the depth for the comparison from the parsed l10n.ini.

    Overloaded to get the source depth for fennec and friends.
    '''
    try:
      depth = cp.get('general', 'source-depth')
    except:
      try:
        depth = cp.get('general', 'depth')
      except:
        depth = '.'
    return depth

  def addChild(self, title, path, orig_cp):
    # check if there's a section with details for this include
    # we might have to check a different repo, or even VCS
    # for example, projects like "mail" indicate in
    # an "include_" section where to find the l10n.ini for "toolkit"
    details = 'include_' + title
    if orig_cp.has_section(details):
      branch = orig_cp.get(details, 'mozilla')
      inipath = orig_cp.get(details, 'l10n.ini')
      path = self.basepath + '/' + branch + '/' + inipath
    else:
      path = urljoin(self.baseurl, path)
    cp = SourceTreeConfigParser(path, self.basepath, **self.defaults)
    cp.loadConfigs()
    self.children.append(cp)

  def dirsIter(self):
    if self.tld is not None:
      url = urlparse(self.baseurl)
      basepath = None
      if url[0] == 'file':
        basepath = url2pathname(url[2])
      yield self.tld, (basepath, )
    for t in L10nConfigParser.dirsIter(self):
      yield t


class File(object):
  def __init__(self, fullpath, file, module = None, locale = None):
    self.fullpath = fullpath
    self.file = file
    self.module = module
    self.locale = locale
    pass
  def getContents(self):
    # open with universal line ending support and read
    return open(self.fullpath, 'rU').read()
  def __hash__(self):
    f = self.file
    if self.module:
      f = self.module + '/' + f
    return hash(f)
  def __str__(self):
    return self.fullpath
  def __cmp__(self, other):
    if not isinstance(other, File):
      raise NotImplementedError
    rv = cmp(self.module, other.module)
    if rv != 0:
      return rv
    return cmp(self.file, other.file)

class EnumerateDir(object):
  ignore_dirs = ['CVS', '.svn', '.hg']
  def __init__(self, basepath, module = '', locale = None):
    self.basepath = basepath
    self.module = module
    self.locale = locale
    pass
  def cloneFile(self, other):
    '''
    Return a File object that this enumerator would return, if it had it.
    '''
    return File(os.path.join(self.basepath, other.file), other.file,
                self.module, self.locale)
  def __iter__(self):
    # our local dirs are given as a tuple of path segments, starting off
    # with an empty sequence for the basepath.
    dirs = [()]
    while dirs:
      dir = dirs.pop(0)
      fulldir = os.path.join(self.basepath, *dir)
      try:
        entries = os.listdir(fulldir)
      except OSError:
        # we probably just started off in a non-existing dir, ignore
        continue
      entries.sort()
      for entry in entries:
        leaf = os.path.join(fulldir, entry)
        if os.path.isdir(leaf):
          if entry not in self.ignore_dirs:
            dirs.append(dir + (entry,))
          continue
        yield File(leaf, '/'.join(dir + (entry,)),
                   self.module, self.locale)

class LocalesWrap(object):
  def __init__(self, base, module, locales):
    self.base = base
    self.module = module
    self.locales = locales
  def __iter__(self):
    for locale in self.locales:
      path = os.path.join(self.base, locale, self.module)
      yield (locale, EnumerateDir(path, self.module, locale))

class EnumerateApp(object):
  reference =  'en-US'
  def __init__(self, inipath, l10nbase, locales = None):
    self.setupConfigParser(inipath)
    self.modules = defaultdict(dict)
    self.l10nbase = os.path.abspath(l10nbase)
    self.filters = []
    drive, tail = os.path.splitdrive(inipath)
    filterpath = drive + url2pathname(urlparse(urljoin(tail,'filter.py'))[2])
    self.addFilters(*self.config.getFilters())
    self.locales = locales or self.config.allLocales()
    self.locales.sort()
    pass
  def setupConfigParser(self, inipath):
    self.config = L10nConfigParser(inipath)
    self.config.loadConfigs()
  def addFilters(self, *args):
    self.filters += args

  value_map = {None:None, 'error':0, 'ignore':1, 'report':2}
  def filter(self, l10n_file, entity = None):
    '''Go through all added filters, and,
    - map "error" -> 0, "ignore" -> 1, "report" -> 2
    - if filter.test returns a bool, map that to
      False -> "ignore" (1), True -> "error" (0)
    - take the max of all reported
    '''
    rv = 0
    for f in reversed(self.filters):
      try: 
        _r = f(l10n_file.module, l10n_file.file, entity)
      except:
        # XXX error handling
        continue
      if isinstance(_r, bool):
        _r = [1, 0][_r]
      else:
        # map string return value to int, default to 'error', None is None
        _r = self.value_map.get(_r, 0)
      if _r is not None:
        rv = max(rv, _r)
    return ['error','ignore','report'][rv]

  def __iter__(self):
    '''
    Iterate over all modules, return en-US directory enumerator, and an
    iterator over all locales in each iteration. Per locale, the locale
    code and an directory enumerator will be given.
    '''
    dirmap = dict(self.config.directories())
    mods = dirmap.keys()
    mods.sort()
    for mod in mods:
      if self.reference == 'en-US':
        base = os.path.join(*(dirmap[mod] + ('locales', 'en-US')))
      else:
        base = os.path.join(self.l10nbase, self.reference, mod)
      yield (mod, EnumerateDir(base, mod, self.reference),
             LocalesWrap(self.l10nbase, mod, self.locales))


class EnumerateSourceTreeApp(EnumerateApp):
  '''Subclass EnumerateApp to work on side-by-side checked out
  repos, and to no pay attention to how the source would actually
  be checked out for building.

  It's supporting applications like Fennec, too, which have
  'locales/en-US/...' in their root dir, but claim to be 'mobile'.
  '''

  def __init__(self, inipath, basepath, l10nbase, locales=None):
    self.basepath = basepath
    EnumerateApp.__init__(self, inipath, l10nbase, locales)

  def setupConfigParser(self, inipath):
    self.config = SourceTreeConfigParser(inipath, self.basepath)
    self.config.loadConfigs()


def get_base_path(mod, loc):
  'statics for path patterns and conversion'
  __l10n = 'l10n/%(loc)s/%(mod)s'
  __en_US = 'mozilla/%(mod)s/locales/en-US'
  if loc == 'en-US':
    return __en_US % {'mod': mod}
  return __l10n % {'mod': mod, 'loc': loc}

def get_path(mod, loc, leaf):
  return get_base_path(mod, loc) + '/' + leaf

