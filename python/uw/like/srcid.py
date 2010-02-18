"""
$Header$

author: Eric Wallace <wallacee@uw.edu>

"""import os
import math
from glob import glob
import numpy as np
import pyfits as pf
from skymaps import SkyDir
from uw.utilities.fitstools import trap_mask, rad_mask


class SourceAssociation(object):
    """A class to find association probabilities for sources with a given set of counterpart catalogs."""

    def __init__(self,catdir):
        cat_files = glob(os.path.join(catdir,'*.fits'))
        self.catalogs = dict(zip([os.path.basename(cat)[:-5] for cat in cat_files],
                                 [Catalog(cat) for cat in cat_files]))

    def id(self,position,error,catalog,prior_prob = .5,prob_threshold=.5):
        """Given a skydir and error ellipse, return associations from catalogs.

        Arguments:
            position    : A SkyDir representing the location of the source to be associated.
            error       : Either the radius of a 1-sigma error circle (r68), or a sequence
                          of length 3 representing major and minor axes and position angle of an
                          error ellipse
            catalog    : A catalog name (name of catalog file, without .fits extension,e.g. 'obj-agn')
            prob_threshold: Probability threshold for considering a source associated.

        Returns all sources with posterior probability greater than prob_threshold,
        sorted by probability.
        """

        try:
            error_maj_axis,error_min_axis,error_angle = [math.radians(x) for x in error]
        except TypeError:
            #error not a sequence, assume that it's a 1-sigma error circle radius 
            error_maj_axis,error_min_axis,error_angle = [math.radians(error)]*2+[0]
        except ValueError:
            #error is a sequence, but not of length 3.  If it's a single value, 
            #assume it's a circular error; otherwise, complain and return None.
            if len(error) == 1:
                error_maj_axis,error_min_axis,error_angle = [math.radians(error[0])]*2+[0]
            else:
                print 'Wrong length for argument "error".'
                return
        associations = []
        cat = self.catalogs[catalog]
        #filter sources by position, ~5-sigma radius
        sources = cat.select_circle(position,math.degrees(error_maj_axis)*5)
        post_probs = []
        for source in sources:
            #Compute angular separation and position angle
            angsep = position.difference(source.skydir)
            ra1,dec1,ra2,dec2 = [math.radians(x) for x in
                                (position.ra(),position.dec(),
                                source.skydir.ra(),source.skydir.dec())]
            denom = math.sin(dec1)*math.cos(ra1-ra2) - math.cos(dec1)*math.tan(dec2)
            posang = math.atan2(math.sin(ra1-ra2), denom)

            #Compute delta(logl), assuming elliptical parabaloid shape.
            phi = posang-error_angle
            delta = .5*angsep**2*((math.cos(phi)/error_maj_axis)**2 +
                                   (math.sin(phi)/error_min_axis)**2)
            norm = 2.*math.pi*error_maj_axis*error_min_axis
            pos_prob = math.exp(-delta)/norm

            #Compute chance association prob (=local catalog density)
            #Should be consistent with 1FGL method.
            chance_prob = cat.local_density(position)

            #Calculate posterior probability
            arg = (chance_prob*(1-prior_prob)/(pos_prob*prior_prob))
            post_prob = 1./(1.+arg)
            post_probs += [post_prob]
        #return sources above threshold, sorted by posterior probability
        source_list = [(prob,source) for prob,source in zip(post_probs,sources) if prob > prob_threshold]
        source_list.sort()
        return source_list


class Catalog(object):
    """A class to manage the relevant information from a FITS catalog."""

    def __init__(self,catalog):
        self.cat_name = os.path.basename(catalog).split('.')[0]
        self.coords = SkyDir.EQUATORIAL
        try:
            fits_cat = pf.open(catalog)
        except IOError:
            raise CatalogError(catalog,'Error opening catalog file. Not a FITS file?')
        #Find hdu with catalog information
        self.hdu = self._get_hdu(fits_cat)
        if self.hdu is None:
            raise CatalogException(catalog,'No catalog information found.')
        names = self._get_ids()
        if names is None:
            raise CatalogException(catalog,'Could not find column with source names')
        lons,lats = self._get_positions()
        if lons is None:
            raise CatalogException(catalog,'Could not find columns with source positions')
        self.sources = np.array([CatalogSource(self,name,SkyDir(lon,lat,self.coords))
                        for name,lon,lat in zip(names,lons,lats)])

    def __iter__(self):
        return self.sources

    def _get_hdu(self,fits_cat):
        """Find and return HDU with catalog information."""
        #First check for HDUS with CAT-NAME or EXTNAME in header.
        for hdu in fits_cat:
            cards = hdu.header.ascardlist()
            try:
                self.cat_name = cards['CAT-NAME'].value
                return hdu
            except KeyError:
                try:
                    self.cat_name = cards['EXTNAME'].value
                    return hdu
                except KeyError:
                    pass
        #No CAT-NAME or EXTNAME found, just return second HDU
        if len(fits_cat)>=2:
            return fits_cat[1]
        #Only one HDU, no name info, return None
        return

    def _get_ids(self):
        """Find source name information and return as a list."""

        name_key = ''
        cards = self.hdu.header.ascardlist()
        #First check for UCD in header
        for card in cards:
            if card.key[:5]=='TBUCD' and card.value == 'ID_MAIN':
                name_key = cards['TTYPE'+card.key[5:8]].value
                break
            #Sometimes UCDs are declared in comments
            #May be fragile - depends on specific format for comments as in gamma-egr catalog
            value_comment = card._getValueCommentString().split('/')
            if len(value_comment)>1:
                comment = value_comment[1]
                ucd_string = comment[comment.find('UCD'):].split()
                if ucd_string:
                    try:
                        if ucd_string[0].split('=')[1].strip('.')=='ID_MAIN':
                            name_key = cards[''.join(['TTYPE',card.key[5:8]])].value
                            break
                    except IndexError:
                        pass
            if card.key[:5]=='TTYPE' and card.value.upper() in ['NAME','ID']:
                name_key = card.value
        try:
            return self.hdu.data.field(name_key)
        except KeyError:
            return
        names = self.hdu.data.field(name_key)

    def _get_positions(self):
        """Find columns containing position info and return a list of SkyDirs"""

        cards = self.hdu.header.ascardlist()
        ucds = cards.filterList('TBUCD*')
        ttypes = cards.filterList('TTYPE*')
        lon_key = lat_key = ''
        if not lon_key:
            if 'POS_EQ_RA_MAIN' in ucds.values():
                ucd = ucds.keys()[ucds.values().index('POS_EQ_RA_MAIN')]
                lon_key = ttypes[''.join(['TTYPE',ucd[5:8]])].value
                #Assumes that if POS_EQ_RA_MAIN exists, POS_EQ_DEC_MAIN does too.
                ucd = ucds.keys()[ucds.values().index('POS_EQ_DEC_MAIN')]
                lat_key = ttypes[''.join(['TTYPE',ucd[5:8]])].value
            elif 'RAdeg' in ttypes.values():
                lon_key = ttypes[ttypes.keys()[ttypes.values().index('RAdeg')]].value
                lat_key = ttypes[ttypes.keys()[ttypes.values().index('DEdeg')]].value
            elif '_RAJ2000' in ttypes.values():
                lon_key = ttypes[ttypes.keys()[ttypes.values().index('_RAJ2000')]].value
                lat_key = ttypes[ttypes.keys()[ttypes.values().index('_DEJ2000')]].value
            elif 'RAJ2000' in ttypes.values():
                lon_key = ttypes[ttypes.keys()[ttypes.values().index('RAJ2000')]].value
                lat_key = ttypes[ttypes.keys()[ttypes.values().index('DEJ2000')]].value
            elif 'RA' in ttypes.values():
                lon_key = ttypes[ttypes.keys()[ttypes.values().index('RA')]].value
                lat_key = ttypes[ttypes.keys()[ttypes.values().index('DE')]].value
        if not lon_key:
            self.coords = SkyDir.GALACTIC
            if 'POS_GAL_LON' in ucds.values():
                lon_key = ucds.keys()[ucds.values().index('POS_GAL_LON')]
                lat_key = ucds.keys()[ucds.values().index('POS_GAL_LAT')]
            elif '_GLON' in ttypes.values():
                lon_key = ttypes[ttypes.keys()[ttypes.values().index('_GLON')]].value
                lat_key = ttypes[ttypes.keys()[ttypes.values().index('_GLAT')]].value
            elif 'GLON' in ttypes.values():
                lon_key = ttypes[ttypes.keys()[ttypes.values().index('GLON')]].value
                lat_key = ttypes[ttypes.keys()[ttypes.values().index('GLAT')]].value
        if lon_key:
            return (self.hdu.data.field(lon_key).astype('float'),
                    self.hdu.data.field(lat_key).astype('float'))
        else:
            return

    def _get_errors(self,dat):
        """Find columns with position errrors."""
        pass

    def select_circle(self,position,radius):
        """Return an array of CatalogSources within radius degrees of position.

        Arguments:
            position    : SkyDir for center of selection region.
            radius      : radius of selection region.
        """

        ras = np.array([source.skydir.ra() for source in self.sources])
        decs = np.array([source.skydir.dec() for source in self.sources])
        tmask = trap_mask(ras,decs,position,radius)
        ras,decs = ras[tmask],decs[tmask]
        rmask = rad_mask(ras,decs,position,radius)[0]
        return self.sources[tmask][rmask]

    def local_density(self,position,radius=4):
        """Return the local density of catalog sources in a radius-degree region about position."""

        n_sources = len(self.select_circle(position,radius))
        solid_angle = radius**2*math.pi
        return n_sources/solid_angle


class CatalogSource(object):
    """A class representing a catalog source."""
    def __init__(self,catalog,name,skydir):
        self.catalog = catalog
        self.name = name
        self.skydir = skydir

    def __str__(self):
        return '\t'.join([self.catalog.cat_name,self.name,str(self.skydir.ra()),str(self.skydir.dec())])

class CatalogError(Exception):
    """Exception class for problems with a catalog."""
    def __init__(self,catalog,message):
        self.catalog = catalog
        self.message = message
    def __str__(self):
        return 'In catalog %s:\n\t%s'%(self.catalog,self.message)

def test(cat_dir=r'd:\fermi\catalog\srcid\cat'):
    assoc = SourceAssociation(cat_dir)
    #3C 454.3
    pos, error = SkyDir(343.495,16.149), .016/2.45
    print([x[1].name for x in assoc.id(pos,error,'obj-blazar-crates',.33,.8)])
    #Couldn't find elliptical errors, but want to test input for error.
    error = (error,error,0.0)
    print([x[1].name for x in assoc.id(pos,error,'obj-blazar-crates',.33,.8)])


if __name__=='__main__':
    assoc = SourceAssociation('/home/eric/research/catalog/counterpartCatalogs')
    #3C 454.3
    pos, error = SkyDir(343.495,16.149), .016/2.45
    print('\n'.join([str(x[1]) for x in assoc.id(pos,error,'obj-blazar-crates',.33,.8)]))
    #Couldn't find elliptical errors, but want to test input for error.
    error = (error,error,0.0)
    print('\n'.join([str(x[1]) for x in assoc.id(pos,error,'obj-blazar-crates',.33,.8)]))
    #Test for correct failure for wrong length list
    #error = [.5]*4
    #print(assoc.id(pos,error,'obj-agn',.039,.9735))
