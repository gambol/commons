from collections import defaultdict
from contextlib import contextmanager
import os
import hashlib
from twitter.common.collections import OrderedSet
from twitter.common.dirutil import safe_open
from twitter.pants import get_buildroot
from twitter.pants.base import BuildFile, ParseContext
from twitter.pants.targets import Pants
from twitter.pants.goal.products import Products

class Context(object):
  class Log(object):
    def debug(self, msg): pass
    def info(self, msg): pass
    def warn(self, msg): pass

  def __init__(self, config, options, target_roots, log=None):
    self.config = config
    self.options = options
    self.log = log or Context.Log()
    self._state = {}
    self.products = Products()

    self.replace_targets(target_roots)

  def identify(self, targets):
    id = hashlib.md5()
    for target in targets:
      id.update(target.id)
    return id.hexdigest()

  def __str__(self):
    return 'Context(id:%s, state:%s, targets:%s)' % (self.id, self.state, self.targets())

  def replace_targets(self, target_roots):
    self.target_roots = target_roots
    self._targets = OrderedSet()
    for target in target_roots:
      self._add_target(target)
    self.id = self.identify(self._targets)

  def _add_target(self, target):
    def add_targets(tgt):
      self._targets.update(t for t in tgt.resolve())
    target.walk(add_targets)

  def add_target(self, build_dir, target_type, *args, **kwargs):
    target = self._do_in_context(lambda: target_type(*args, **kwargs), build_dir)
    self._add_target(target)
    return target

  def targets(self, predicate=None):
    return filter(predicate, self._targets)

  def dependants(self, on_predicate=None, from_predicate=None):
    core = set(self.targets(on_predicate))
    dependees = defaultdict(set)
    for target in self.targets(from_predicate):
      if hasattr(target, 'dependencies'):
        for dependency in target.dependencies:
          if dependency in core:
            dependees[target].add(dependency)
    return dependees

  def resolve(self, spec):
    return self._do_in_context(lambda: Pants(spec).resolve())

  def _do_in_context(self, work, path=None):
    # TODO(John Sirois): eliminate the need for all the gymanstics needed to synthesize a target
    build_dir = path or self.config.getdefault('pants_workdir')
    build_path = os.path.join(build_dir, 'BUILD.pants')
    if not os.path.exists(build_path):
      with safe_open(build_path, 'w') as build_file:
        build_file.write('# dummy BUILD file generated by pants\n')

    return ParseContext(BuildFile(get_buildroot(), build_path)).do_in_context(work)

  @contextmanager
  def state(self, key, default=None):
    value = self._state.get(key, default)
    yield value
    self._state[key] = value
