"""
All like2 testing code goes here, using unittest
$Header: /nfs/slac/g/glast/ground/cvs/pointlike/python/uw/like2/test.py,v 1.5 2013/11/10 20:28:59 burnett Exp $
"""
import os, sys, unittest
import numpy as np
import skymaps
from skymaps import SkyDir, Band

from uw.like2 import ( configuration, 
    diffusedict as diffuse,
    sources,
    exposure,
    extended,
    roisetup,
    dataset,
    bandlike,
    )
from uw.like2.configuration import Bandlite # for testing.

# to define the configuration
config = None
ecat = None
bands=None

def setup_config_dir(skymodelname='P202/uw29'):
    return os.path.join(os.path.expandvars('$HOME/skymodels'),skymodelname)
    
class TestSetup(unittest.TestCase):
    def setUp(self, force=False):
        """Configuration assuming P202_uw29, back 133 MeV"""
        global config
        if config is None:
            self.config_dir=setup_config_dir()
            config =  configuration.Configuration(self.config_dir, quiet=True, postpone=True)
        self.config = config
        self.skydir = Band(12).dir(2)#SkyDir()
        
class TestConfig(TestSetup):
    """Test aspects of the configuration
    """
    
    def test_psf(self):
        """check that the PSF is set up
        """
        psf = self.config.psfman(1, 1000)
        self.assertDictContainsSubset(dict(event_type=1, energy=1000), psf.__dict__)
        psf.setEnergy(133)
        self.assertEquals(133, psf.energy)
        self.assertAlmostEqual(81.0904920, psf(0)[0], msg='value expected with IRF for pass 7')
        
    def test_exposure(self):
        """check exposure"""
        exposure = self.config.exposureman(1, 1000)
        self.assertDictContainsSubset(dict(et=1, energy=1000), exposure.__dict__, 'full dict: %s'%exposure.__dict__)
        exposure.setEnergy(133)
        self.assertEquals(133, exposure.energy)
        self.assertAlmostEqual(2.1604e10 , exposure(self.skydir), delta=1e8)
        
    def test_exposure_integral(self, expect=921.5):
        """test the exposure integral at a point
        """
        emin, e, emax = np.logspace(2, 2.25, 3)
        exp = self.config.exposureman(1, e)
        model = sources.PowerLaw(1e-11,2)
        f1 = exposure.ExposureIntegral(exp,self.skydir, emin, emax)(model)
        f = lambda model : exp.model_integral(self.skydir, model, emin, emax)
        f2 = f(model) #exp.model_integral(self.skydir, model, emin, emax)
        self.assertAlmostEquals(f1,f2, delta=1e-2)
        self.assertAlmostEquals(expect, f1, delta=0.1)
        # need to check value print f2, f(model.gradient), (f(sources.PowerLaw(1.1e-11,2))-f(model))
        
    def test_bandlite(self):
        """ check bandlite"""
        band = Bandlite(self.skydir, self.config)
        self.assertDictContainsSubset(dict(radius=5, event_type=1), band.__dict__, str(band.__dict__))

class TestDiffuse(TestSetup):
    
    def setUp(self, **kwargs):
        super(TestDiffuse,self).setUp(**kwargs)
        self.back_band = Bandlite(self.skydir,self.config, event_type=1)
        self.front_band = Bandlite(self.skydir,self.config, event_type=0)
        
    def test_factory(self):
        """test the factory setup """
        for t in ['junk.txt', ('junk.txt','t'),'tst_PowerLaw(1e-11, c )', 
                      dict(file='template_4years_P7_v15_repro_v2_4bpd.zip'),
                  ]:
            self.assertRaises(diffuse.DiffuseException, diffuse.diffuse_factory, t )
            
        test_values = [ 
                ('isotrop_4years_P7_V15_repro_v2_source_front.txt', 
                    'isotrop_4years_P7_V15_repro_v2_source_back.txt'),
                dict(filename='template_4years_P7_v15_repro_v2_4bpd.zip',
                        correction='../../P202/uw29/galactic_correction_uw26a_v2.csv', 
                        systematic=0.0316),
                'template_4years_P7_v15_repro_v2.fits',
                'limb_PowerLaw(1e-11, 4.0)',
                ]
        for t in test_values:
            diffuse.diffuse_factory(t)

        ## test that evaluting returns the same object id
        ids = map(lambda f: id(diffuse.diffuse_factory(f)[0]), [test_values[i] for i in (0,1,0)])
                
        self.assertEquals(ids[0],ids[2], msg='expect the same object')
        self.assertNotEquals(ids[0],ids[1], msg='expect different objects')
        
        
    def test_isotrop(self):
        """istropic source with constant model"""
        source = sources.GlobalSource(name='isotrop', skydir=None,
            model=sources.Constant(1.0),
            dmodel=diffuse.diffuse_factory(['isotrop_4years_P7_V15_repro_v2_source_%s.txt'%s 
                                            for s in self.config.event_class_names]))
        self.resp =resp=source.response(self.back_band)
        self.assertAlmostEquals(4626, resp.counts, delta=1) # warning: seems to be 4850 in old version
        self.assertAlmostEquals(193864, resp(resp.roicenter), delta=10)

    def test_cached_galactic(self):
        """cached galactic source"""
        source = sources.GlobalSource(name='ring', skydir=None,
                model=sources.Constant(1.0),
                dmodel = diffuse.diffuse_factory(dict(filename='template_4years_P7_v15_repro_v2_4bpd.zip'))
                )
        resp= source.response(self.back_band)
        self.response_check(resp, (747, 1391, 57312))
        
    def load_map_cube(self):
        return sources.GlobalSource(name='ring1', skydir=None,
                model=sources.Constant(1.0),
                dmodel = diffuse.diffuse_factory(dict(filename='template_4years_P7_v15_repro_v2.fits'))
                )
        
    def test_map_cube(self):
        """a MapCube source"""
        source = self.load_map_cube()
        resp= source.response( self.back_band)
        self.response_check(resp, (742, 1381, 56876))

    def test_map_cube_front(self):
        """a MapCube source"""
        source = self.load_map_cube()
        resp= source.response( self.front_band)
        self.response_check(resp, (618, 1151, 46894))

    def load_healpix(self):
        source = sources.GlobalSource(name='ring2', skydir=None,
                model=sources.Constant(1.0),
                dmodel = diffuse.diffuse_factory(dict(
                    filename='template_4years_P7_v15_repro_v2_nside256_bpd4.fits',
                    type='Healpix',  ))
                )
        return source

    def response_check(self, resp, expect):
        self.assertAlmostEquals(expect[0], resp.ap_average, delta=1)
        if len(expect)==1: return
        self.assertAlmostEquals(expect[1], resp.counts, delta=1) 
        if len(expect)==2: return
        self.assertAlmostEquals(expect[2], resp(resp.roicenter), delta = 100)

    def test_healpix(self):
        """a Healpix source"""
        source = self.load_healpix()
        self.resp =resp= source.response(self.back_band)
        self.response_check(resp, (722, 1344, 55354))

    def test_healpix_front(self):
        """a Healpix source"""
        source = self.load_healpix()
        self.resp =resp= source.response(self.front_band)
        self.response_check(resp, (602, 1120,  45657))
        
    def test_limb(self):
        source = sources.GlobalSource(name='limb', skydir=None,
            model = sources.FBconstant(2.0, 1.0),
            dmodel=diffuse.diffuse_factory('limb_PowerLaw(1e-11, 4.0)'))
        self.resp_back = source.response(self.back_band)
        self.assertAlmostEquals(1272, self.resp_back.counts, delta=1)
        self.resp_front = source.response(self.front_band)
        self.assertAlmostEquals(1068, self.resp_front.counts, delta=1)
    
class TestPoint(TestSetup):
    def setUp(self, **kwargs):
        super(TestPoint,self).setUp(**kwargs)
        self.back_band = Bandlite(self.skydir,self.config)
  
    
    def test_point(self):
        """response of point source at the center"""
        ptsrc =sources.PointSource(name='test', skydir=self.skydir, 
                                           model=sources.PowerLaw(1e-11, 2.0))
        self.resp =resp = ptsrc.response(self.back_band)
        self.assertAlmostEquals(0.65, resp.overlap, delta=0.01)
        self.assertAlmostEquals(1.0, resp._exposure_ratio)
        self.assertAlmostEquals(600, resp.counts, delta=1.)
        self.assertAlmostEquals(75042, resp(resp.source.skydir), delta=10)
        
    def make_test_source(self, offset, expected_overlap):
        model = sources.PowerLaw(1e-11,2.0)
        source = sources.PointSource(name='test source', 
            skydir=SkyDir(self.skydir.ra(), self.skydir.dec()+offset), model=model)
        conv = source.response(self.back_band) 
        overlap = conv.overlap
        self.assertAlmostEqual(expected_overlap, overlap, delta=0.001)
        #a,b = conv.evaluate_at([source.skydir, self.back_band.sd])/1e12
        #c = conv(source.skydir)/1e12
        #self.assertAlmostEqual(a,c)
        
    def test_create_2deg(self):
        self.make_test_source(2, 0.604)
    def test_create_6deg(self):
        self.make_test_source(4, 0.450)
   
class TestExtended(TestSetup):

    def setUp(self):
        super(TestExtended, self).setUp()
        global ecat
        if ecat is None:
            ecat = extended.ExtendedCatalog(self.config.extended)


    def extended(self, source_name='W28', roi=None, expect=(0,), psf_check=True, model=None, quiet=True):
        source = ecat.lookup(source_name)
        if model is not None:
            source.model = model
        self.assertIsNotNone(source, 'Source %s not in catalog'%source_name)
        b12 = skymaps.Band(12);
        roi_index=roi if roi is not None else b12.index(source.skydir)
        roi_dir = b12.dir(roi_index) 
        difference = np.degrees(roi_dir.difference(source.skydir))
        band = Bandlite(roi_dir, self.config)
        if not quiet:
            print 'Using ROI #%d, distance=%.2f deg' %( roi_index, difference)
            print 'Testing source "%s at %s" with band parameters' % (source, source.skydir)
            for item in band.__dict__.items():
                print '\t%-10s %s' % item
        self.resp = conv = source.response(band)
        if not quiet:
            print 'overlap: %.3f,  exposure_ratio: %.3f' %( conv.overlap,conv.exposure_ratio)
            print 'PSF overlap: %.3f'% conv.psf_overlap
        self.assertAlmostEqual(expect[0], conv.overlap, delta=1e-2)
        if psf_check:
            self.assertAlmostEqual(conv.overlap, conv.psf_overlap, delta=1e-2)
        if len(expect)>1:
            self.assertAlmostEqual(expect[1], conv.counts, delta=10)
        
    def test_W28(self):
        self.extended('W28', expect=(0.65,3483), 
            model=sources.LogParabola(3.38e-11, 2.27, 0.127, 1370))
    def test_W30_in840(self):
        self.extended('W30', 840, expect=(0.377,1038,), 
            model=sources.LogParabola(1.31e-11,2.15, 0.036, 1430) )
    def test_LMC(self):
        self.extended('LMC', expect=(0.593,), psf_check=False)

    def test_Cygnus_Cocoon(self):
        self.extended('Cygnus Cocoon', expect=(0.551,), psf_check=False)

class TestLoadROI(TestSetup):

    def setUp(self, roi_index=840):
        super(TestLoadROI, self).setUp()
        global ecat
        if ecat is None:
            ecat = extended.ExtendedCatalog(self.config.extended, quiet=True)
        self.roi_sources = roisetup.ROImodel(config, ecat=ecat, roi_index=roi_index) 

    def test_loaded(self, roi_index=840):
        roi = self.roi_sources
        self.assertEquals(13, len(roi.local_sources))
        self.assertEquals(4, len(roi.global_sources))
        self.assertEquals(65, len(roi.neighbor_sources))
        
        
class TestLikelihood(TestLoadROI):
    def setUp(self, roi_index=840):
        super(TestLikelihood, self).setUp()
        self.front_band = Bandlite(None, self.config, event_type=0, roi_index=roi_index)
        self.back_band = Bandlite(None, self.config, event_type=1, roi_index=roi_index)
        self.all_bands = configuration.BandSet(self.config, roi_index)
        print 'loaded', self.all_bands
        sources, freelist = self.roi_sources.prep_for_likelihood()
        self.bl = bandlike.factory(self.all_bands[:], sources, freelist)
        
    def test_unweight(self):
        self.assertAlmostEquals(0.092, self.bl[0].make_unweight().round(3))
        self.assertAlmostEquals(0.033, self.bl[1].make_unweight().round(3))

    
        
def test_suite(t):
    return unittest.TestLoader().loadTestsFromTestCase(t)
    
def run(t='all'): 
    if t=='all':
        suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    else:
        suite = unittest.TestLoader().loadTestsFromTestCase(t)
    print 'running %d tests' % suite.countTestCases()
    unittest.TextTestRunner(stream=sys.stdout,verbosity=2).run(suite)
    
if __name__=='__main__':
    run()