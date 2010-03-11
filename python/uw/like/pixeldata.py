"""
Manage data and livetime information for an analysis


    $Header: /nfs/slac/g/glast/ground/cvs/pointlike/python/uw/like/pixeldata.py,v 1.6 2010/03/11 19:23:29 kerrm Exp $

"""
version='$Revision: 1.6 $'.split()[1]
import os
import math
import skymaps
import pointlike
import pyfits


class PixelData(object):
    """
Create a new PixelData instance, managing data and livetime.

    analysis_environment: an instance of AnalysisEnvironment correctly configured with
                          the location of files needed for spectral analysis (see its
                          docstring for more information.)

Optional keyword arguments:

   see docstring for SpectralAnalysis
"""

    def __init__(self, spectral_analysis ):
        """
Create a new PixelData instance, managing data and livetime.

    analysis_environment: an instance of AnalysisEnvironment correctly configured with
                          the location of files needed for spectral analysis (see its
                          docstring for more information.)

Optional keyword arguments:

   see docstring for SpectralAnalysis
"""

        self.__dict__.update(spectral_analysis)

        from numpy import arange,log10
        self.my_bins = 10**arange(log10(self.emin),log10(self.emax*1.01),1./self.binsperdec)
        self.binner_set = False

        # check explicit files
        for filelist in [self.ft1files, self.ft2files] :
            if filelist is not None and len(filelist)>0 and not os.path.exists(filelist[0]):
                raise Exception('PixelData setup: file name or path "%s" not found'%filelist[0])

        # order of operations: GTI is needed for livetime; livetime is needed for PSF
        self.gti  =  self._GTI_setup()
        self.lt   =  self.get_livetime()
        self._PSF_setup()
        self.data = self.get_data()
        self.dmap = self.data.map()
        self.dmap.updateIrfs()

    def __str__(self):
        return 'Pixeldata: %.3f M events, %.3f Ms' % (self.dmap.photonCount()/1e6, self.gti.computeOntime()/1e6)

    def __repr__(self):
        return str(self)

    def reload_data(self,ft1files):
        self.ft1files = ft1files if type(ft1files)==type([]) or ft1files is None else [ft1files]
        for filelist in  [self.ft1files, self.ft2files] :
            if filelist is not None and len(filelist)>0 and not os.path.exists(filelist[0]):
                raise Exception('PixelData setup: file name or path "%s" not found'%filelist[0])
        self.data = self.get_data()
        self.dmap = self.data.map()
        self.dmap.updateIrfs()

    def fill_empty_bands(self,bpd):

        from pointlike import Photon
        from skymaps import SkyDir
        dummy = SkyDir(0,0)
        bands = self.my_bins

        for bin_center in (bands[:-1]*bands[1:])**0.5:
             ph_f = Photon(dummy,bin_center,2.5e8,0)
             ph_b = Photon(dummy,bin_center,2.5e8,1)
             bpd.addBand(ph_f)
             bpd.addBand(ph_b)

    def _Data_setup(self):

        from numpy import arccos,pi
        pointlike.Data.set_class_level(self.event_class)
        pointlike.Data.set_zenith_angle_cut(self.zenithcut)
        pointlike.Data.set_theta_cut(self.thetacut)
        pointlike.Data.set_use_mc_energy(self.mc_energy)
        pointlike.Data.set_Gti_mask(self.gti)
        if not self.quiet: print '.....set Data theta cut at %.1f deg'%(self.thetacut)

        if not self.binner_set:
            from pointlike import DoubleVector
            self.binner = skymaps.PhotonBinner(DoubleVector(self.my_bins))
            pointlike.Data.setPhotonBinner(self.binner)
            self.binner_set = True

    def _PSF_setup(self):

        # modify the psf parameters in the band objects
        # note there is a small discrepancy since the PSF average does not
        # currently know about the theta cut
        ip = skymaps.IParams
        #if self.ltcube is not None and self.roi_dir is not None:
           #ip.set_livetimefile(self.ltcube)
           #ip.set_skydir(self.roi_dir)
        ip.set_CALDB(self.CALDB)
        ip.init('_'.join(self.irf.split('_')[:-1]),self.irf.split('_')[-1])

    def _GTI_setup(self):
        """Create the GTI object that will be used to filter photon events and
           to calculate the livetime.

           Generally, one will have run gtmktime on the FT1 file(s) provided
           to filter out large excursions in rocking angle, and/or make a
           a cut for when a (small) ROI is too close to the horizon.

           gti_mask is an optional kwarg to provide an additional GTI object that
           can, e.g., be used to filter out GRBs.  An intersection with the GTIs
           from the FT1 files and this gti_mask is made.
        """
        print 'applying GTI'
        gti = skymaps.Gti(self.ft1files[0])

        # take the union of the GTI in each FT1 file
        for ef in self.ft1files[1:]:
            gti.combine(skymaps.Gti(ef))
        tmax = self.tstop if self.tstop > 0 else gti.maxValue()

        gti = gti.applyTimeRangeCut(self.tstart,tmax) #save gti for later use

        if 'gti_mask' in self.__dict__ and self.gti_mask is not None:
            before = gti.computeOntime()
            gti.intersection(self.gti_mask)
            if not self.quiet: print 'applied gti mask, before, after times: %.1f, %.1f' % (before, gti.computeOntime())

        return gti

    def get_data(self):

        #if no binned object present, create; apply cuts
        if self.binfile is None or not os.path.exists(self.binfile):

            self._Data_setup()

            if self.verbose: print 'loading file(s) %s' % self.ft1files
            data = pointlike.Data(self.ft1files,self.conv_type,self.tstart,self.tstop,self.mc_src_id,'')

            self.fill_empty_bands(data.map())     # fill any empty bins

            if self.verbose: print 'done'
            if self.binfile is not None:
                if not self.quiet: print '.....saving binfile %s for subsequent use' % self.binfile
                data.write(self.binfile)
                
                """
                # a start on adding keywords -- not yet finished, but need to merge in CVS
                # now, add the appropriate entries to the FITS header
                f = pyfits.open(self.binfile)
                h = f[1].header
                pos = len(h.keys)
                entries = []
                entries += ['EMIN', self.emin, 'Minimum energy in MeV']
                entries += ['EMAX', self.emax, 'Maximum energy in MeV']
                entries += ['BINS_PER_DECADE', self.binsperdec, 'Number of (logarithmic) energy bins per decade']
                entries += ['TMIN', self.tmin, 'Exclude all data before this MET']
                entries += ['TMAX', self.tmax, 'Exclude all data after this MET']
                entries += ['EVENT_CLASS', self.event_class, 'Exclude all data with class level < this value']
                entries += ['CONVERSION_TYPE', self.event_class, '0 = Front only, 1 = Back only, -1 = Front + Back']
                
                for entry in entries:
                    k,v,c = entry
                    h.update(k,str(v),c)
                
                f.writeto(self.binfile,clobber=True)
                f.close()
                """
        
        else:
            data = pointlike.Data(self.binfile)
            if not self.quiet: print '.....loaded binfile %s ' % self.binfile

        if self.verbose:
            data.map().info()
            print '---------------------'

        return data

    def test_pixelfile_consistency(self):
        """Check the keywords in a binned photon data header for consistency with the analysis environment."""
        pass

    def get_livetime(self,   pixelsize=1.0):

        gti = self.gti

        if self.ltcube is None or not os.path.exists(self.ltcube):
            if self.roi_dir is None:
                # no roi specified: use full sky
                self.roi_dir = skymaps.SkyDir(0,0)
                self.exp_radius = 180

            lt = skymaps.LivetimeCube(
                cone_angle =self.exp_radius,
                dir        =self.roi_dir,
                zcut       =math.cos(math.radians(self.zenithcut)),
                pixelsize  =pixelsize,
                quiet      =self.quiet )

            for hf in self.ft2files:
                if not self.quiet: print 'loading FT2 file %s' %hf ,
                lt_gti = skymaps.Gti(hf,'SC_DATA')
                if not ((lt_gti.maxValue() < self.gti.minValue()) or
                        (lt_gti.minValue() > self.gti.maxValue())):
                   lt.load(hf,gti)

            # write out ltcube if requested
            if self.ltcube is not None: lt.write(self.ltcube)
        else:
            # ltcube exists: just use it! (need to bullet-proof this)
            lt = skymaps.LivetimeCube(self.ltcube)
            if not self.quiet: print 'loaded LivetimeCube %s ' % self.ltcube
        return lt


#--------------------------------------------------------------------
# test for this application
#--------------------------------------------------------------------

def setup(bins=8):
    data_path = r'f:\glast\data\flight'
    months = ['aug', 'sep', 'oct']
    event_files  = [os.path.join(data_path, '%s2008-ft1.fits'%m) for m in months ]
    history_files= [os.path.join(data_path, '%s2008-ft2.fits'%m) for m in months ]
    return PixelData( event_files, history_files,
        livetimefile='../data/aug-oct_livetime.fits',
        datafile='../data/aug-oct2008_%d.fits'%bins,
        binsperdec=bins)
if __name__=='__main__':
    pass
