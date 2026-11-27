import importlib.util, time, unittest
from pathlib import Path
from unittest.mock import patch
spec = importlib.util.spec_from_file_location('acore', str(Path(__file__).with_name('renew_acorehost.py')))
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
class TestAcore(unittest.TestCase):
 def test_unknown_does_not_renew(self):
  with patch.object(a,'req') as req:
   self.assertEqual(a.renew_server('id',None),(False,'expiry_unknown'));req.assert_not_called()
 def test_48_hours(self):
  with patch.object(a.time,'time',return_value=1000), patch.object(a,'req',return_value=(422,{'error':'Renewal is available when less than 8 hours remain'})) as req:
   self.assertEqual(a.renew_server('id',1000+48*3600+1),(True,'not_due'));req.assert_not_called()
   self.assertEqual(a.renew_server('id',1000+48*3600),(True,'not_due'));req.assert_called_once()
 def test_confirm_expiry(self):
  now=time.time()
  with patch.object(a,'req',return_value=(200,{'renewed':True})),patch.object(a.time,'sleep'),patch.object(a,'get_details',return_value={'plan_expires_at':now+7200}):
   self.assertEqual(a.renew_server('id',now+3600),(True,'renewed'))
  with patch.object(a,'req',return_value=(200,{'renewed':True})),patch.object(a.time,'sleep'),patch.object(a,'get_details',return_value={}):
   self.assertEqual(a.renew_server('id',now+3600),(False,'unverified'))
 def test_starting_wait_no_restart(self):
  with patch.object(a,'get_state',return_value=('starting',500,100)), patch.object(a,'wait_running',return_value=False), patch.object(a,'req') as req:
   self.assertFalse(a.ensure_running('id',False));req.assert_not_called()
 def test_offline_still_tries_start(self):
  with patch.object(a,'get_state',return_value=('offline',0,0)), patch.object(a,'wait_running',return_value=True), patch.object(a,'req',return_value=(200,{})) as req:
   self.assertTrue(a.ensure_running('id',False));self.assertEqual(req.call_args.kwargs['body'],{'server':'id'})
 def test_no_repeat_when_transfer(self):
  with patch.object(a,'get_state',return_value=('offline',0,0)),patch.object(a,'wait_running',return_value=False),patch.object(a,'req',return_value=(422,{'message':'Wait for the storage transfer'})) as req:
   self.assertFalse(a.ensure_running('id',False));req.assert_called_once()
 def test_unknown_expiry_still_checks_and_no_restore(self):
  with patch.object(a,'get_details',return_value={}), patch.object(a,'ensure_running',return_value=True) as start,patch.object(a,'req') as req:
   ok,row=a.inspect_server({'uuid':'1','is_suspended':True});self.assertFalse(ok);start.assert_called_once();req.assert_not_called()
 def test_count_once(self):
  with patch.object(a,'req',return_value=(200,{'servers':{'data':[{'uuid':'1'},{'uuid':'2'}]}})),patch.object(a,'inspect_server',side_effect=[(True,('1',)),(False,('2',))]):
   ok,total,rows=a.pass_once();self.assertEqual((ok,total,len(rows)),(1,2,2))
if __name__=='__main__': unittest.main()
