"""
Analyze the contents of HEALPix tables, especially the tsmap

$Header: /nfs/slac/g/glast/ground/cvs/pointlike/python/uw/like2/analyze/hptables.py,v 1.11 2016/04/27 02:22:06 burnett Exp $

"""

import os, glob, time, pyfits
import numpy as np
import pylab as plt
import pandas as pd

from matplotlib.colors import LogNorm
from uw.like2.pub import healpix_map
from skymaps import Band, SkyDir
from . import analysis_base, sourceinfo
from ..pipeline import check_ts, ts_clusters
from analysis_base import html_table, FloatFormat


class HPtables(sourceinfo.SourceInfo):
    """Process tables 
    <br>Includes TS residual map files generated by the "table" UWpipeline analysis stage, 
    generating list of new seeds 
    %(tsmap_analysis)s
    """
    require = 'ts_table' ## fix.
    def setup(self, **kw):

        self.nside = nside= kw.pop('nside', 512)
        self.tsname = tsname=kw.pop('tsname', 'ts')
        self.input_path=kw.pop('input_path', '.')
        self.input_model=os.path.realpath(self.input_path).split('/')[-1]
        # get the 
        super(HPtables, self).setup(**kw)
        self.title = '{} Table analysis'.format(self.tsname)
        fnames = glob.glob(os.path.join(self.input_path, 'hptables_*_%d.fits' % nside ))
        
        assert len(fnames)>0, '''did not find hptables_*_%d.fits file:
                 try runing healpix_map.assembele_tables''' %nside

        self.fname=None
        for fname in fnames:
            t = fname.split('_')
            if tsname in t:
                print 'Found table %s in file %s' %(tsname, fname)
                self.fname=fname
                break
        assert self.fname is not None, 'Table %s not found in files %s' %(tsname, fnames)

        self.tables = pd.DataFrame(pyfits.open(self.fname)[1].data)
        print 'loaded file {}, created {}'.format(self.fname, 
            time.asctime(time.localtime(os.path.getmtime(self.fname))))
        self.tsmap=healpix_map.HParray(self.tsname, self.tables[self.tsname])
        self.kdemap=healpix_map.HParray('kde', self.tables.kde) if 'kde' in self.tables else None

        self.plotfolder = 'hptables_%s' % tsname
        self.seedfile, self.seedroot, self.bmin = \
            'seeds_%s.txt'%tsname, '%s%s'%( (tsname[-1]).upper(),self.input_model[-3:] ) , 0
        
        self.make_seeds(refresh=kw.pop('refresh', False))

    
    def make_seeds(self, refresh=False,  tcut=10, bcut=0, minsize=1):
        """ may have to run the clustering application """
        if not os.path.exists(self.seedfile) or os.path.getsize(self.seedfile)==0 or refresh:
               # or os.path.getmtime(self.seedfile)<os.path.getmtime(self.fname)\
               
            print 'reconstructing seeds: %s --> %s: ' % (self.fname, self.seedfile),
            rec = open(self.seedfile, 'w')
            skymodel=self.skymodel
            
            # Special check for a month, which should mask out the Sun
            if skymodel.startswith('month'):
                month=int(skymodel[5:]);
                mask = check_ts.monthly_ecliptic_mask( month)
                print 'created a mask for month %d, with %d pixels set' % (month, sum(mask))
            else: mask=None

            # Create the seed list by clustering the pixels in the tsmap
            nseeds = check_ts.make_seeds('test', self.fname, fieldname=self.tsname, 
                nside=self.nside, rcut=tcut, bcut=bcut, rec=rec, 
                seedroot=self.seedroot, minsize=minsize,
                mask=~mask if mask is not None else None)
            print '%d seeds' % nseeds
            if nseeds==0:
                self.seeds = None
                self.n_seeds = 0
                return
            if not os.path.exists(self.seedfile):
                raise Exception( 'Failed to create file %s' %self.seedfile)
        self.seeds = pd.read_table(self.seedfile, index_col=0)
        skydirs = map(SkyDir, self.seeds.ra, self.seeds.dec)
        self.seeds['roi'] = map(Band(12).index, skydirs)
        
        # add info from fit, if there
        self.seeds['ts_fit'] = self.df.ts
        self.seeds['locqual'] = self.df.locqual
        self.seeds['pindex'] = self.df.pindex
        self.seeds['bad'] = [np.isnan(x) for x in self.seeds.ts_fit]

        self.n_seeds = len(self.seeds)
        print 'read in %d seeds from %s' % (self.n_seeds, self.seedfile)
        outfile = 'seeds_{}.csv'.format(self.tsname)
        self.seeds.to_csv(outfile)
        print 'wrote csv file {} with fit info, if any'.format(outfile)
        
        self.tsmap_analysis="""<p>Seed analysis parameters: 
            <dl>
            <dt>seedfile</dt><dd><a href="../../%s?skipDecoration">%s</a> </dd>_
            <dt>seedroot</dt><dd> %s</dd>
            <dt>bmin</dt>    <dd> %s</dd> 
            </dl>""" % (self.seedfile, self.seedfile, self.seedroot,  self.bmin)

    
    def kde_map(self, vmin=1e5, vmax=1e7, pixelsize=0.25):
        """Photon Density map
        All data, smoothed with a kernel density estimator using the PSF.
        """
        hpts = self.kdemap
        if hpts is None: return
        hpts.plot(ait_kw=dict(pixelsize=pixelsize), norm=LogNorm(vmin, vmax))
        fig=plt.gcf()
        fig.set_facecolor('white')
        return fig
     
    def ts_map(self, vmin=0, vmax=25, pixelsize=0.25):
        """ TS residual map 
        DIstribution of TS values for %(title)s residual TS study.
        """
        self.tsmap.plot(ait_kw=dict(pixelsize=pixelsize), vmin=vmin, vmax=vmax)
        fig=plt.gcf()
        fig.set_facecolor('white')
        return fig
        
    def seed_plots(self, bcut=5, subset=None, title=None):
        """ Seed plots
        
        Results of cluster analysis of the residual TS distribution. Analysis of %(n_seeds)d seeds from file 
        <a href="../../%(seedfile)s">%(seedfile)s</a>. 
        <br>Left: size of cluster, in 0.15 degree pixels
        <br>Center: maximum TS in the cluster
        <br>Right: distribution in sin(|b|), showing cut if any.
        """
        z = self.seeds if subset is None else self.seeds[subset]
        fig,axx= plt.subplots(1,3, figsize=(12,4))
        plt.subplots_adjust(left=0.1)
        bc = np.abs(z.b)<bcut
        histkw=dict(histtype='step', lw=2)
        def all_plot(ax, q, dom, label):
            ax.hist(q.clip(dom[0],dom[-1]),dom, **histkw)
            ax.hist(q[bc].values.clip(dom[0],dom[-1]),dom, color='orange', label='|b|<%d'%bcut, **histkw)
            plt.setp(ax, xlabel=label, xlim=(None,dom[-1]))
            ax.grid()
            ax.legend(prop=dict(size=10))
        all_plot(axx[0], z.size, np.linspace(0.5,10.5,11), 'cluster size')
        all_plot(axx[1], z.ts, np.linspace(0,50,26), 'TS')
        all_plot(axx[2], np.sin(np.radians(z.b)), np.linspace(-1,1,41), 'sin(b)')
        axx[2].axvline(0, color='k')
        fig.suptitle('{} {} seeds from model {}'.format( len(z), self.tsname, self.input_model,)
             if title is None else title)
        fig.set_facecolor('white')
        return fig
        
    def bad_seed_plots(self):
        """Plots of the %(bad_seeds)d seeds that were not imported to the model
        Mostly this is because there was no sensible localization. The table below has the localization
        TS map plots for each one, linked to the source name.
        <br>Left: size of cluster, in 0.15 degree pixels
        <br>Center: maximum TS in the cluster
        <br>Right: distribution in sin(|b|), showing cut if any.
        %(bad_seed_list)s
        """
        self.bad_seeds = sum(self.seeds.bad)
        s='Bad seed list'
        df = self.seeds[self.seeds.bad]['ra dec ts size l b roi'.split()].sort_index(by='roi')
        df.to_csv(self.plotfolder+'/bad_seeds.csv')
        print 'Wrote file {}'.format(self.plotfolder+'/bad_seeds.csv')
        s+= html_table(df, name=self.plotfolder+'/bad_seeds', 
                heading='<h4>Table of %d failed seeds</h4>'%self.bad_seeds,
                href_pattern='tsmap_fail/%s_tsmap.jpg',
                float_format=FloatFormat(2))
        self.bad_seed_list = s
        return self.seed_plots(subset=self.seeds.bad, title='{} failed seeds'.format(self.bad_seeds))
        
    def pixel_ts_distribution(self):
        """The cumulative TS distribution
        For single pixels, one might expect the chi-squared distribution for the null hypothesis if 
        there were no resolvable sources, and the background model was correct.
        The shaded area is the difference.
        """
        fig,ax = plt.subplots(figsize=(8,6))
        bins = np.linspace(0,25,501)
        tsvec=self.tsmap.vec
        ax.hist(tsvec, bins, log=True, histtype='step', lw=2, cumulative=-1, label='data');
        # make array corresponding to the hist
        h = np.histogram(tsvec, bins, )[0]
        x = bins[:-1]
        yh = sum(h)-h.cumsum() 
        f = lambda x: np.exp(-x/2)
        ye=6e5*f(x)
        ax.plot(x, ye, '-g', lw=2, label='exp(-TS/2)')
        ax.fill_between(x,yh,ye,where=x>5, facecolor='red', alpha=0.6)
        plt.setp(ax, xscale='linear', xlabel='TS', ylim=(1,None), ylabel='# greater than TS')
        ax.legend()
        ax.set_title('Cumulative distribution of single-pixel TS values for {}'.format(self.skymodel),
                     fontsize=14)
        ax.grid(True, alpha=0.5)        
        fig.set_facecolor('white')
        return fig
    
    def plot_region(self, loc, size=2, pixelsize=0.01, title=None, galactic=True):
        fig, (ax1,ax2) = plt.subplots(1,2, figsize=(16,8))
        z1= self.tsmap.plot_ZEA(loc, size=size, pixelsize=pixelsize, axes=ax1, vmin=10, vmax=25)
        z2= self.kdemap.plot_ZEA(loc, size=size, pixelsize=pixelsize, axes=ax2)
        fig.set_facecolor('white')
        return fig
        
    
    def all_plots(self):
        self.runfigures([ self.kde_map, self.ts_map, self.pixel_ts_distribution, self.seed_plots, self.bad_seed_plots])
