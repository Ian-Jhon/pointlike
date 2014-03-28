"""
Analyze the contents of HEALPix tables, especially the tsmap

$Header: /nfs/slac/g/glast/ground/cvs/pointlike/python/uw/like2/analyze/hptables.py,v 1.3 2014/03/27 20:54:21 burnett Exp $

"""

import os, glob, pyfits
import numpy as np
import pylab as plt
import pandas as pd

from matplotlib.colors import LogNorm
from uw.like2.pub import healpix_map
from . import analysis_base
from ..pipeline import check_ts, ts_clusters

class HPtables(analysis_base.AnalysisBase):
    """Process Healpix tables, including TS residual map files generated by the "table" UWpipeline analysis stage, 
    perhaps generating list of new seeds 
    %(tsmap_analysis)s
    """
    require = 'ts_table' ## fix.
    def setup(self, **kw):
        self.nside = nside= kw.pop('nside', 512)
        fnames = glob.glob('hptables_*_%d.fits' % nside )
        assert len(fnames)>0, 'did not find hptables_*_%d.fits file' %nside
        self.fname=fnames[0]
        self.tables = pd.DataFrame(pyfits.open(self.fname)[1].data)
        self.plotfolder = 'hptables'
        self.tsname='ts'
        self.seedfile, self.seedroot, self.title, self.bmin = 'seeds.txt', 'SEED' ,'power-law', 0
        self.make_seeds(refresh=kw.pop('refresh', False))
        self.tsmap_analysis="""<p>Seed analysis parameters: 
            <dl>
            <dt>seedfile</dt><dd><a href="../../%s?skipDecoration">%s</a> </dd>
            <dt>seedroot</dt><dd> %s</dd>
            <dt>bmin</dt>    <dd> %s</dd> 
            </dl>""" % (self.seedfile, self.seedfile, self.seedroot,  self.bmin)

     
    def make_seeds(self, refresh=False,  tcut=10, bcut=0, minsize=2):
        """ may have to run the clustering application """
        if not os.path.exists(self.seedfile) or os.path.getmtime(self.seedfile)<os.path.getmtime(self.fname) or refresh:
            print 'reconstructing seeds: %s --> %s: ' % (self.fname, self.seedfile),
            rec = open(self.seedfile, 'w')
            nseeds = check_ts.make_seeds(self.tsname, nside=self.nside, rcut=tcut, bcut=bcut, rec=rec, seedroot=self.seedroot, minsize=minsize)
            print '%d seeds' % nseeds
            if not os.path.exists(self.seedfile):
                raise Exception( 'Failed to create file %s' %self.seedfile)
        self.seeds = pd.read_table(self.seedfile)
        self.n_seeds = len(self.seeds)
        print 'read in %d seeds from %s' % (self.n_seeds, self.seedfile)
    
    def kde_map(self, vmin=1e5, vmax=1e8, pixelsize=0.25):
        """Photon Density map
        All data, smoothed with a kernel density estimator using the PSF.
        """
        hpts = healpix_map.HParray('kde', self.tables.kde)
        hpts.plot(ait_kw=dict(pixelsize=pixelsize), norm=LogNorm(vmin, vmax))
        return plt.gcf()
     
    def ts_map(self, vmin=10, vmax=25, pixelsize=0.25):
        """ TS residual map 
        DIstribution of TS values for %(title)s residual TS study.
        """
        hpts = healpix_map.HParray(self.tsname, self.tables[self.tsname])
        hpts.plot(ait_kw=dict(pixelsize=pixelsize), vmin=vmin, vmax=vmax)
        return plt.gcf()
        
    def seed_plots(self, bcut=5):
        """ Seed plots
        
        Results of cluster analysis of the residual TS distribution. Analysis of %(n_seeds)d seeds from file 
        <a href="../../%(seedfile)s">%(seedfile)s</a>. 
        <br>Left: size of cluster, in 0.15 degree pixels
        <br>Center: maximum TS in the cluster
        <br>Right: distribution in sin(|b|), showing cut if any.
        """
        z = self.seeds
        fig,axx= plt.subplots(1,3, figsize=(12,4))
        plt.subplots_adjust(left=0.1)
        bc = np.abs(z.b)<bcut
        def all_plot(ax, q, dom, label):
            ax.hist(q.clip(dom[0],dom[-1]),dom)
            ax.hist(q[bc].clip(dom[0],dom[-1]),dom, color='orange', label='|b|<%d'%bcut)
            plt.setp(ax, xlabel=label)
            ax.grid()
            ax.legend(prop=dict(size=10))
        all_plot(axx[0], z.size, np.linspace(0,20,21), 'cluster size')
        all_plot(axx[1], z.ts, np.linspace(0,50,26), 'TS')
        all_plot(axx[2], np.sin(np.radians(z.b)), np.linspace(-1,1,41), 'sin(b)')
        axx[2].axvline(0, color='k')
        return fig
    
    def all_plots(self):
        self.runfigures([ self.seed_plots, self.ts_map, self.kde_map,])