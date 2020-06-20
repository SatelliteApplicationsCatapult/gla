import os
import re
import sys
import glob
from datetime import datetime

# logging
from contextlib import redirect_stdout
from contextlib import redirect_stderr

# otb imports
import otbApplication

# local imports
from src.utility import ps
from src.utility import parser
from src.utility.bbox import BBox

class Dataset:

    def __init__(   self, 
                    scene, 
                    **kwargs  ):

        """
        constructor
        """

        # initialised by derived instances
        self._tle = None 
        self._platform = None
        self._norad_id = []

        # multispectral / panchromatic
        self._image_ids = [ 'MS', 'P' ]
        self._scene = scene

        # get attributes
        self._datetime = self.getDateTimeString( scene )

        # optional arguments + default values
        self._dem_path = kwargs.pop('dem_path', None)
        self._geoid_pathname = kwargs.pop( 'geoid_pathname', None ) 
        self._epsg = kwargs.pop('epsg', None )
        self._pan_method = kwargs.pop('pan_method', None )
        self._roi = None
        
        # create bbox object
        coords = kwargs.pop('roi', None )
        if coords is not None:
            self._roi = BBox( coords )

        # set default ram usage
        self._ram = kwargs.pop('ram', 4096)
        os.environ['OTB_MAX_RAM_HINT'] = str( self._ram )

        # setup log file
        log_path = kwargs.pop('log', 'D:\\data\\log' )
        if not os.path.exists( log_path ):
            os.makedirs( log_path )

        # capture stdout  
        log_pathname = os.path.join( log_path, os.path.basename( scene ).replace( '.zip', '.log' ) )  
        self._log = open( log_pathname, 'w', buffering=1 )

        return


    @staticmethod
    def getId( scene ):

        """
        get identity of dataset
        """

        _id = None
        for item in[ 'PHR', 'SPOT' ]:

            # spot or pleiades dataset
            if item in os.path.basename( scene ):
                _id = item
                break

        return _id


    def getSubPath( self ):

        """
        retrieve satellite name and tle from pathname
        """

        # construct unique tle / datetime folder name
        return os.path.join( self._tle, self._datetime )


    def getDateTimeString( self, scene ):

        """
        retrieve scene acquisition datetime from pathname
        """

        return self.getDateTime( scene ).strftime( '%Y%m%d_%H%M%S' )


    def getPlatform( self, scene, exp ):

        """
        retrieve satellite name and tle from pathname
        """

        platform = None

        # identify platform name
        filename = os.path.basename( scene )
        m = re.search( exp, filename )
        if m:
            platform =  str(m.group(0) ).strip( '_' )

        return platform


    def getDateTime( self, scene ):

        """
        retrieve scene acquisition datetime from pathname
        """

        dt = None

        # identify satellite name
        filename = os.path.basename( scene )
        m = re.search( '_[0-9]{15}_', filename )
        if m:

            # strip name and retrieve tle from dict
            value =  str(m.group(0) ).strip( '_' )
            dt = datetime.strptime( str( value ), '%Y%m%d%H%M%S%f')
            
        return dt


    def getTile( self, pathname ):

        """
        get tile code from filename
        """

        tile = None

        # identify tile code
        if os.path.splitext( pathname )[1].upper() == '.TIF':

            # apply regexp
            m = re.search( '_R[0-9]{1}C[0-9]{1}', os.path.basename( pathname ) )
            if m:
                tile =  str(m.group(0) ).strip( '_' )
            
        return tile


    def getTileCoordinates( self, pathname ):

        """
        get tile code from filename
        """

        coords = []        

        # get tile substr R*C*
        tile = self.getTile( pathname )
        if tile is not None:
            
            # strip digits 
            coords = re.findall(r'\d+', tile )

        return coords


    def getImageLists( self, path ):

        """
        get pathnames of multispectral and panchromatic images in dataset
        """

        # get dataset image lists
        images = {}
        for _id in self._image_ids:

            # glob search path and sort lists
            image_path = os.path.join( path, '**/IMG_{platform}_{id}_*/IMG_{platform}_{id}_*.TIF'.format ( platform=self._platform, id=_id ) )
            images[ _id ] = glob.glob( image_path, recursive=True )


        return images


    def getSrtmTiles( self, images ):

        """
        download srtm tiles overlapping image list
        """

        if self._dem_path is not None:

            # create app and populate parameter values
            app = otbApplication.Registry.CreateApplication('DownloadSRTMTiles')

            app.SetParameterStringList( 'il', images )
            app.SetParameterString( 'tiledir', self._dem_path )

            # execute download
            with redirect_stdout( self._log ), redirect_stderr( self._log ):
                app.ExecuteAndWriteOutput()

        return


    def getCalibratedImages( self, images, out_path, level='toa', milli=True ):

        """
        generate optical calibration images
        """

        # create application
        app = otbApplication.Registry.CreateApplication('OpticalCalibration')

        out_images = []
        for image in images:

            # check out pathname exists
            out_pathname = os.path.join( out_path, os.path.basename( image ).replace( '.TIF', '_CAL.TIF' ) )
            if not os.path.exists( out_pathname ):

                # create out path if required
                if not os.path.exists( out_path ):
                    os.makedirs( out_path )

                # initialise arguments
                app.SetParameterString('in', image )
                app.SetParameterString('level', level )            
                app.SetParameterString('out', out_pathname + '?&gdal:co:TILED=YES' )

                # output to 0 -> 1000 16bit rather than 0 -> 1.0 32bit float
                app.SetParameterString('milli', str( milli ) )            
                if milli:
                    app.SetParameterOutputImagePixelType('out', otbApplication.ImagePixelType_uint16 )

                # execute and write products
                with redirect_stdout( self._log ), redirect_stderr( self._log ):
                    app.ExecuteAndWriteOutput()

            # add to list
            out_images.append( out_pathname )

        return out_images


    def getTileFusionImages( self, images, out_path ):

        """
        generate optical calibration images
        """

        out_pathname = None

        # loop through image tiles
        nrows = 0; ncols = 0
        for image in images:
            
            # get max column and row
            coords = self.getTileCoordinates( image )

            nrows = max( nrows, int( coords[ 0 ] ) )
            ncols = max( ncols, int ( coords[ 1 ] ) )

        # validate sufficient imagery in list                
        if len( images ) == nrows * ncols:

            if len( images ) > 1:

                # create application + sort into lexiographic order
                app = otbApplication.Registry.CreateApplication('TileFusion')
                images.sort()

                # replace tile code of first image basename with mosaic label
                out_pathname = os.path.join( out_path, os.path.basename( images[ 0 ] ).replace( '_R1C1', '_MOSAIC' ) )
                if not os.path.exists( out_pathname ):

                    # create out path if required
                    if not os.path.exists( out_path ):
                        os.makedirs( out_path )

                    # initialise arguments
                    app.SetParameterStringList('il', images )
                    app.SetParameterString('out', out_pathname + '?&gdal:co:TILED=YES' )
                    app.SetParameterInt('cols', ncols )
                    app.SetParameterInt('rows', nrows )

                    # execute and write products
                    with redirect_stdout( self._log ), redirect_stderr( self._log ):
                        app.ExecuteAndWriteOutput()

            else:
                
                # single image - no need to fuse
                out_pathname = images[ 0 ]

        return out_pathname


    def getRoiImage( self, image, out_path ):

        """
        get aoi images
        """

        # create application
        app = otbApplication.Registry.CreateApplication('ExtractROI')
        out_pathname = None

        # get roi coordinates
        coords = self._roi.getImageRoi( image )
        if coords is not None: 

            # check out pathname exists
            out_pathname = os.path.join( out_path, os.path.basename( image ).replace( '.TIF', '_ROI.TIF' ) )
            if not os.path.exists( out_pathname ):

                # create out path if required
                if not os.path.exists( out_path ):
                    os.makedirs( out_path )

                # setup input and output
                app.SetParameterString( 'in', image )
                app.SetParameterString( 'out', out_pathname + '?&gdal:co:TILED=YES' )
                app.SetParameterString( 'mode', 'extent' )

                # copy corner coordinates of aoi
                app.SetParameterFloat( 'mode.extent.ulx', coords[ 0 ] )
                app.SetParameterFloat( 'mode.extent.uly', coords[ 1 ] )
                app.SetParameterFloat( 'mode.extent.lrx', coords[ 2 ] )
                app.SetParameterFloat( 'mode.extent.lry', coords[ 3 ] )

                # execute download
                with redirect_stdout( self._log ), redirect_stderr( self._log ):
                    app.ExecuteAndWriteOutput()

        return out_pathname


    def getPansharpenImage_Bundle( self, images, out_path ):

        """
        generate pansharpened images
        """

        # create app
        app = otbApplication.Registry.CreateApplication('BundleToPerfectSensor')
                                
        # create output pathname
        out_pathname = os.path.join( out_path, os.path.basename( images[ 'MS' ] ).replace( '_MS_', '_PAN_' ) )
        if not os.path.exists( out_pathname ):

            # create out path if required
            if not os.path.exists( out_path ):
                os.makedirs( out_path )

            # initialise parameters
            app.SetParameterString('inp', images[ 'P' ] )
            app.SetParameterString('inxs', images[ 'MS' ] )
            app.SetParameterString('out', out_pathname + '?&gdal:co:TILED=YES' )

            # configure elevation parameters
            if self._dem_path is not None and self._geoid_pathname is not None:
                app.SetParameterString('elev.dem', self._dem_path )
                app.SetParameterString('elev.geoid', self._geoid_pathname )

            # set method (rcs, lvms, bayes)
            if self._pan_method is not None:
                    app.SetParameterString('method', self._pan_method )

            # generate pansharpen images
            with redirect_stdout( self._log ), redirect_stderr( self._log ):
                app.ExecuteAndWriteOutput()

        return out_pathname


    def getSuperimposedImage( self, images, out_path ):

        """
        generate multispectral image superimposed to panchromatic image geometry
        """

        # create app
        app = otbApplication.Registry.CreateApplication('Superimpose')
                                
        # create output pathname
        out_pathname = os.path.join( out_path, os.path.basename( images[ 'MS' ] ).replace( '_MS_', '_MS_SUPER_' ) )
        if not os.path.exists( out_pathname ):

            # create out path if required
            if not os.path.exists( out_path ):
                os.makedirs( out_path )

            # initialise parameters
            app.SetParameterString('inr', images[ 'P' ] )
            app.SetParameterString('inm', images[ 'MS' ] )
            app.SetParameterString('out', out_pathname + '?&gdal:co:TILED=YES' )

            # configure elevation parameters
            if self._dem_path is not None and self._geoid_pathname is not None:
                app.SetParameterString('elev.dem', self._dem_path )
                app.SetParameterString('elev.geoid', self._geoid_pathname )

            # generate pansharpen images
            with redirect_stdout( self._log ), redirect_stderr( self._log ):
                app.ExecuteAndWriteOutput()

        return out_pathname


    def getPansharpenImage( self, images, out_path ):

        """
        generate multispectral image superimposed to panchromatic image geometry
        """

        # create app
        app = otbApplication.Registry.CreateApplication('Pansharpening')
                                
        # create output pathname
        out_pathname = os.path.join( out_path, os.path.basename( images[ 'MS' ] ).replace( '_MS_SUPER_', '_PAN_' ) )
        if not os.path.exists( out_pathname ):

            # create out path if required
            if not os.path.exists( out_path ):
                os.makedirs( out_path )

            # initialise parameters
            app.SetParameterString('inp', images[ 'P' ] )
            app.SetParameterString('inxs', images[ 'MS' ] )
            app.SetParameterString('out', out_pathname + '?&gdal:co:TILED=YES&gdal:co:COMPRESS=DEFLATE&gdal:co:BIGTIFF=YES' )

            # set method (rcs, lvms, bayes)
            if self._pan_method is not None:
                app.SetParameterString('method', self._pan_method )

            # generate pansharpen images
            with redirect_stdout( self._log ), redirect_stderr( self._log ):
                app.ExecuteAndWriteOutput()

        return out_pathname
