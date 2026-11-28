import unittest
from unittest.mock import patch
import minely_keepalive as m

class Fake:
 def __init__(self,states,fail=False):self.states=iter(states);self.calls=0;self.fail=fail
 def health(self):return next(self.states)
 def start(self):
  self.calls+=1
  if self.fail:raise TimeoutError('unknown')
  return 204

class Tests(unittest.TestCase):
 def test_actual_health_shape(self):self.assertEqual(m.health_state({'ok':True,'resources':{'current_state':'running'}}),'running')
 def test_unknown_and_node_lost_fail_closed(self):
  for d in [{},{'ok':False,'node_lost':True},{'ok':True,'resources':{}},{'ok':True,'installing':True,'resources':{'current_state':'offline'}}]:
   with self.assertRaises(RuntimeError):m.health_state(d)
 def test_csrf_and_home_links(self):
  self.assertEqual(m.parse_page('<input name="_token" value="abc"><meta name="csrf-token" content="def">').csrf,'def')
  self.assertTrue(m.home_has_server('<a href="https://minely.net/my/s/'+m.SERVER_ID+'">Open</a>'))
  self.assertFalse(m.home_has_server('<a href="https://evil.test/my/s/'+m.SERVER_ID+'">Open</a>'))
 @patch.object(m.time,'sleep')
 def test_running_never_starts(self,_):
  f=Fake(['running']);self.assertTrue(m.ensure_running(f));self.assertEqual(f.calls,0)
 @patch.object(m.time,'sleep')
 def test_offline_then_running(self,_):
  f=Fake(['offline','starting','running']);self.assertTrue(m.ensure_running(f));self.assertEqual(f.calls,1)
 @patch.object(m.time,'sleep')
 def test_start_exception_not_repeated(self,_):
  f=Fake(['offline','starting','running'],True);self.assertTrue(m.ensure_running(f));self.assertEqual(f.calls,1)
 @patch.object(m.time,'sleep')
 def test_starting_not_started(self,_):
  f=Fake(['starting','running']);self.assertTrue(m.ensure_running(f));self.assertEqual(f.calls,0)
 @patch.object(m.time,'sleep')
 def test_stopping_then_offline(self,_):
  f=Fake(['stopping','offline','running']);self.assertTrue(m.ensure_running(f));self.assertEqual(f.calls,1)
 def test_starting_not_success(self):
  f=Fake(['starting']);self.assertFalse(m.ensure_running(f,wait_seconds=0));self.assertEqual(f.calls,0)
 def test_unknown_health_never_start(self):
  class Bad:
   def health(self):raise RuntimeError()
   def start(self):raise AssertionError('must not start')
  self.assertFalse(m.ensure_running(Bad()))
if __name__=='__main__':unittest.main()
