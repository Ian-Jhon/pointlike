"""
Classes for pipeline processing
$Header: /nfs/slac/g/glast/ground/cvs/pointlike/python/uw/like2/process.py,v 1.17 2014/07/01 17:46:14 burnett Exp $

"""
import os, sys, time, pickle
import numpy as np
import pandas as pd
from skymaps import SkyDir, Band
from uw.utilities import keyword_options
from uw.like2 import (main, tools, sedfuns, maps, sources, localization, roimodel,)


class Process(main.MultiROI):

    defaults=(
        ('outdir',        '.',   'output folder'),
        ('localize_flag', False, 'perform localiation'),
        ('localize_kw',   {},    'keywords for localization'),
        ('repivot_flag',  False, 'repivot the sources'),
        ('betafix_flag',  False, 'check betas, refit if needed'),
        ('dampen',        1.0,   'damping factor: set <1 to dampen, 0 to not fit'),
        ('counts_dir',    None,  'folder for the counts plots'),
        ('norms_first',   False, 'initial fit to norms only'),
        ('countsplot_tsmin', 100, 'minimum for souces in counts plot'),
        ('source_name',   None,   'for localization?'),
        ('fit_kw',        {},     'extra parameters for fit'),
        ('associate_flag',False,  'run association'),
        ('tsmap_dir',     None,   'folder for TS maps'),
        ('sedfig_dir',    None,   'folder for sed figs'),
        ('quiet',         False,  'Set false for summary output'),
        ('finish',        False,  'set True to turn on all "finish" output flags'),
        ('residual_flag', False,  'set True for special residual run; all else ignored'),
        ('tables_flag',   False,  'set True for tables run; all else ignored'),
        ('tables_nside',  512,    'nside to use for table generation'),
        ('seed_flag',     False,  'set True for seed check run'),
        ('update_positions_flag',False,  'set True to update positions before fitting'),
        
    )
    
    @keyword_options.decorate(defaults)
    def __init__(self, config_dir, roi_list=None, **kwargs):
        """ process the roi object after being set up
        """
        keyword_options.process(self, kwargs)
        import matplotlib.pylab as plt
        print 'Backend: %s' % plt.rcParams['backend']
        if self.finish:
            self.__dict__.update(dampen=0,
                                 localize_flag=True, associate_flag=True,
                                 sedfig_dir='sedfig',
                                 counts_dir='countfig', 
                                 tsmap_dir='tsmap_fail',
                                 )
        super(Process,self).__init__(config_dir,quiet=self.quiet)
        self.stream = os.environ.get('PIPELINE_STREAMPATH', 'interactive')
        if roi_list is not None:
            for index in roi_list:
                self.process_roi(index)
        
    def process_roi(self, index):
        """ special for batch: manage the log file, make sure an exception closes it
        """
        print 'Setting up ROI #%04d ...' % index,
        sys.stdout.flush()
        self.setup_roi(index)
        if self.outdir is not None: 
            logpath = os.path.join(self.outdir, 'log')
            if not os.path.exists(logpath): os.mkdir(logpath)
            outtee = tools.OutputTee(os.path.join(logpath, self.name+'.txt'))
        else: outtee=None
        print 'Processing...'
        sys.stdout.flush()
        try:
            self.process()
        finally:
            if outtee is not None: outtee.close()
        
        
    def process(self):
        roi=self
        dampen=self.dampen 
        outdir = self.outdir
        print  '='*80
        print '%4d-%02d-%02d %02d:%02d:%02d - %s - %s' %(time.localtime()[:6]+ (roi.name,)+(self.stream,))

        # special processing flags
        if self.residual_flag:
            self.residuals()
            return
        if self.tables_flag:
            self.tables()
            return
        if self.seed_flag:
            self.seeds()
            return
            
        if self.counts_dir is not None and not os.path.exists(self.counts_dir) :
            try: os.makedirs(self.counts_dir) # in case some other process makes it
            except: pass
        sys.stdout.flush()
        init_log_like = roi.log_like()
        if self.update_positions_flag:
            self.update_positions()
            
        roi.print_summary(title='before fit, logL=%0.f'% init_log_like)
        fit_sources = [s for s in roi.free_sources if not s.isglobal]
        if len(roi.sources.parameters[:])==0 or dampen==0:
            print '===================== not fitting ========================'
        else:
            fit_kw = self.fit_kw
            try:
                if self.norms_first:
                    print 'Fitting parameter names ending in "Norm"'
                    roi.fit('_Norm',  **fit_kw)
                roi.fit(update_by=dampen, **fit_kw)
                change =roi.log_like() - init_log_like 
                if  abs(change)>1.0 :
                    roi.print_summary(title='after global fit, logL=%0.f, change=%.1f'% (roi.log_like(), change))
                    
                if self.repivot_flag:
                    # repivot, iterating a few times
                    n = 3
                    while n>0:
                        if not self.repivot( fit_sources): break
                        n-=1
                if self.betafix_flag:
                    if not self.betafix(roi):
                        print 'betafix requested, but no refit needed, quitting'
            except Exception, msg:
                print '============== fit failed, no update!! %s'%msg
                raise
        
        def getdir(x ):
            if x is None or outdir is None: return None
            t = os.path.join(outdir, x)
            if not os.path.exists(t): os.mkdir(t)
            return t
        sedfig_dir = getdir(self.sedfig_dir)
        if sedfig_dir is not None:
            print '------------ creating seds, figures ---------------'; sys.stdout.flush()
            skymodel_name = os.path.split(os.getcwd())[-1]
            roi.plot_sed('all', sedfig_dir=sedfig_dir, suffix='_sed_%s'%skymodel_name, )
        
        if self.localize_flag:
            print '------localizing all local sources------'; sys.stdout.flush()
            tsmap_dir = getdir(self.tsmap_dir)
            roi.localize('all', tsmap_dir=tsmap_dir)
        
        if self.associate_flag:
            print '-------- running associations --------'; sys.stdout.flush()
            self.find_associations('all')

        print '-------- analyzing counts histogram, ',; sys.stdout.flush()
        cts=roi.get_counts() # always do counts
        print 'chisquared: %.1f ----'% cts['chisq']

        counts_dir = getdir(self.counts_dir)
        if counts_dir is not None:
            print '------- saving counts figure ------'; sys.stdout.flush()
            try:
                fig = roi.plot_counts( tsmin=self.countsplot_tsmin)
                fout = os.path.join(counts_dir, ('%s_counts.jpg'%roi.name) )
                print 'saving counts plot to %s' % fout ; sys.stdout.flush()
                fig.savefig(fout, dpi=60)
            except Exception,e:
                print '***Failed to analyze counts for roi %s: %s' %(roi.name,e)
                chisq = -1
        
        if outdir is not None:  
            pickle_dir = os.path.join(outdir, 'pickle')
            if not os.path.exists(pickle_dir): os.makedirs(pickle_dir)
            roi.to_healpix( pickle_dir, dampen, 
                counts=cts,
                stream=self.stream,
                )
    
    def repivot(self, fit_sources=None, min_ts = 10, max_beta=3.0, emin=200, emax=20000., dampen=1.0):
        """ invoked  if repivot flag set;
        returns True if had to refit, allowing iteration
        """
        roi = self
        print '\ncheck need to repivot sources with TS>%.0f, beta<%.1f: \n'\
        'source                     TS        e0      pivot' % (min_ts, max_beta)
        need_refit =False
        if fit_sources is None:
            fit_sources = [s for s in roi.sources if s.skydir is not None and np.any(s.spectral_model.free)]
        print 'processing %d sources' % len(fit_sources)
        for source in fit_sources:
            model = source.spectral_model
            try:
                ts, e0, pivot = roi.TS(source.name),model.e0, model.pivot_energy()
            except Exception, e:
                print 'source %s:exception %s' %(source.name, e)
                continue
                
            if pivot is None: 
                print 'pivot is none'
                continue
            if model.name=='LogParabola': e0 = model[3]
            elif model.name=='ExpCutoff' or model.name=='PLSuperExpCutoff':
                e0 = model.e0
            else:
                print 'Model %s is not repivoted' % model.name
                continue
            print '%-20s %8.0f %9.0f %9.0f '  % (source.name, ts, e0, pivot),
            if ts < min_ts: 
                print 'TS too small'
                continue
            if model.name=='LogParabola':
                if model[2]>max_beta: 
                    print 'beta= %.2f too large' %(model[2])
                    continue #very 
            if pivot < emin or pivot > emax:
                print 'pivot energy, not in range (%.0f, %.0f): setting to limit' % (emin, emax)
                pivot = min(emax, max(pivot,emin))
            if abs(pivot/e0-1.)<0.05:
                print 'converged'; continue
            print 'will refit'
            need_refit=True
            model.set_e0(pivot*dampen+ e0*(1-dampen))
        if need_refit:
            roi.fit()
        return need_refit
        
    def betafix(self, ts_min=20, qual_min=15,poisson_tolerance=0.2):
        """ invoked  if betafix flag set, 
        if beta=0.001, it has not been tested.
        if beta<0.01 or error exists and  >0.1
        """
        roi = self
        refit=candidate=False
        print 'checking for beta fit: minTS %.1f, min qual %.1f ...' % (ts_min, qual_min)
        models_to_fit=[]
        for source in roi.sources:
            model = source.spectral_model
            which = source.name
            if not np.any(model.free) or model.name!='LogParabola': continue
            if not candidate:
                print 'name                 beta               ts   fitqual'
            candidate=True
            beta = model[2]
            try:
                beta_unc = np.sqrt(model.get_cov_matrix()[2,2])
            except:
                beta_unc=0
            ts = roi.TS(which)
            fit_qual = roi.get_sed(source.name, tol=poisson_tolerance).delta_ts.sum()
            sbeta = ' '*13
            if beta_unc>0:
                sbeta = '%5.3f+/-%5.3f' % (beta, beta_unc) 
            elif beta>0:
                sbeta ='%5.3f        '%beta
            print '%-20s %s %8.0f %8.0f ' %(which, sbeta, ts, fit_qual),
            # beta is free: is it a good fit? check value, error if any
            if model.free[2] or beta>0.001:
                # free: is the fit ok?
                if beta>0.001 and beta_unc>0.001 and beta > 2*beta_unc:
                    print 'ok'
                    if not model.free[2]:
                        source.thaw('beta') # make sure free, since was once.
                        refit=True
                    continue
                else:
                    print '<--- reseting to PowerLaw' 
                    source.freeze('beta')
                    # this should be done by the freeze? dangerous direct access, oh well.
                    model.internal_cov_matrix[2,:]=0
                    model.internal_cov_matrix[:,2]=0
                    model[2]=0.
                    models_to_fit.append(model)
                    refit=True
                    continue
            if beta>0 and beta<=0.001:
                print '<--- freezing at zero'
                model[2]=0
                model.internal_cov_matrix[2,:]=0
                model.internal_cov_matrix[:,2]=0
                continue

            if beta>=3.0: print 'beta>3 too large'; continue
            #if beta==0: print 'frozen previously'; continue
            if ts< ts_min: print 'ts< %.1f'%ts_min; continue # not significant
            if fit_qual < qual_min and beta<=0.01:
                print 'qual<%.1f' %qual_min; 
                continue # already a good fit
            print '<-- select to free beta' # ok, modify
            source.thaw('beta')
            models_to_fit.append(model) # save for later check
            refit = True
        if refit:    
            print 'start refit with beta(s) freed or refixed...'
            roi.sources.initialize()
            roi.fit()
            roi.print_summary(title='after freeing one or more beta parameters')
            # now check for overflow
            refit = False
            for model in models_to_fit:
                beta = model[2]
                if beta < 3.0: continue
                print 'reseting model: beta =%.1f too large' % model[2]
                model.freeze('beta')
                model[0:3]=(1e-15, 2.0, 3.0) #reset everything
                model.cov_matrix[:]=0 
                refit=True
            if refit:
                print 'need to re-refit: beta too large'
                roi.fit()
                roi.print_summary(title='re-refit after freeing/fixing one or more beta parameters')
        else:
            print 'none found'
        return refit    

    def residuals(self, tol=0.3):
        print 'Creating tables of residuals'
        if not os.path.exists('residuals'):
            os.mkdir('residuals')
        resids = sedfuns.residual_tables(self, tol)
        filename = 'residuals/%s_resids.pickle' %self.name
        with open(filename, 'w') as out:
            pickle.dump(resids, out)
            print 'wrote file %s' %filename
            
    def tables(self):
        """ create a set of tables """
        rt = maps.ROItables(self.outdir, nside=self.tables_nside,
               skyfuns= ( 
                (maps.ResidualTS, 'ts', dict(photon_index=2.2),) , 
                (maps.KdeMap,     'kde', dict()),
              ),
)
        rt(self)
        
    def seeds(self,seedfile='seeds.txt', model='PowerLaw(1e-15, 2.2)', 
                prefix='SEED',
                associator=None, tsmap_dir=None,
                **kwargs):
        """ add "seeds" from a text file 
        """
        repivot_flag = kwargs.pop('repivot', True)
        seedcheck_dir = kwargs.get('seedcheck_dir', 'seedcheck')
        if not os.path.exists(seedcheck_dir): os.mkdir(seedcheck_dir)
        associator= kwargs.pop('associate', None)

        seeds = pd.read_table(seedfile)
        seeds['skydir'] = map(SkyDir, seeds.ra, seeds.dec)
        seeds['hpindex'] = map( Band(12).index, seeds.skydir)
        inside = seeds.hpindex==Band(12).index(self.roi_dir)
        seednames=seeds.name[inside]
        if sum(inside)==0:
            print 'no seeds in ROI'
            return
        srclist = []
        for i,s in seeds[inside].iterrows():
            try:
                srclist.append(self.add_source(sources.PointSource(name=s['name'], skydir=s['skydir'], model=model)))
                print 'added %s at %s' % (s['name'], s['skydir'])
            except roimodel.ROImodelException:
                srclist.append(self.get_source(s['name']))
                print 'updating existing %s at %s ' %(s['name'], s['skydir'])
        # Fit only fluxes for each seed first
        parnames = self.sources.parameter_names
        seednorms = np.arange(len(parnames))[np.array([s.startswith(prefix) and s.endswith('_Norm') for s in parnames])]
        self.fit(seednorms)
        # now localize each, moving to new position
        localization.localize_all(self, prefix=prefix, tsmap_dir=tsmap_dir, associator=associator, update=True, tsmin=10)
        # fit full ROI 
        self.fit()
        # save pickled source object for each seed
        for s in srclist:
            s.ts = ts = self.TS(s.name)
            sfile = os.path.join(seedcheck_dir, s.name+'.pickle')
            pickle.dump(s, open(sfile, 'w'))
            print 'wrote file %s' % sfile
            
    def add_sources(self, csv_file='plots/seedcheck/good_seeds.csv'):
        """Add new sources from a csv file
        Default assumes analysis by seedcheck
        """
        assert os.path.exists(csv_file), 'csv file %s not found' % csv_file
        good_seeds = pd.read_csv(csv_file, index_col=0)
        print 'Check %d sources from file %s: ' % (len(good_seeds), csv_file),
        myindex = Band(12).index(self.roi_dir)
        inside = good_seeds['index']==myindex
        ni = sum(inside)
        if ni>0:
            print '%d inside ROI' % ni
        else:
            print 'No sources in ROI %04d' % myindex
            return 
        for name, s in good_seeds[inside].iterrows():
            e0 = s['e0']
            try: #in case already exists (debugging perhaps)
                self.del_source(name)
                print 'replacing source %s' % name 
            except: pass
            source=self.add_source(name=name, skydir=SkyDir(s['ra'],s['dec']), 
                        model=sources.LogParabola(s['eflux']/e0**2/1e6, s['pindex'], s['par2'], e0, 
                                                  free=[True,True,False,False]))
        return good_seeds[inside]   

    def update_positions(self, tsmin=10, qualmax=5):
        """ use the localization information associated with each source to update position
            require ts>tsmin, qual<qualmax
            
        """
        print '---Updating positions---'
        sources = [s for s in self.sources if s.skydir is not None and np.any(s.spectral_model.free)]
        #print 'sources:', [s.name for s in sources]
        print '%-15s%6s%8s %8s' % ('name','TS','qual', 'delta_ts')
        for source in sources:
            print '%-15s %6.0f' % (source.name, source.ts) , 
            if not hasattr(source, 'ellipse') or source.ellipse is None:
                print ' no localization info'
                continue
            if source.ts<tsmin:
                print '    TS<%.0f' % (tsmin)
                continue
            newdir = SkyDir(*source.ellipse[:2]); qual, delta_ts = source.ellipse[-2:]
            print '%6.1f%6.1f' % (qual, delta_ts) ,
            if qual>qualmax:
                print ' qual>%.1f' % qualmax
                continue
            print ' %s -> %s, moved %.2f' % (source.skydir,newdir, np.degrees(newdir.difference(source.skydir)))
            source.skydir = newdir

    

class BatchJob(Process):
    """special interface to be called from uwpipeline
    Expect current dir to be output dir.
    """
    def __init__(self, **kwargs):
        config_dir= kwargs.pop('config_dir', '.')
        roi_list = kwargs.pop('roi_list', range(1,3)) 
        kwargs['outdir']= os.getcwd()
        super(BatchJob, self).__init__(config_dir, **kwargs)
        
    def __call__(self, roi_index):
        self.process_roi(roi_index)
    
#### TODO
#def run(rois, **kw):
#    Process('.', rois, **kw )
#    
#if __name__=='__main__':
#    run()
