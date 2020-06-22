import os

# local imports
from dataset import Dataset
from src.utility import ps

class Pleiades ( Dataset ):

    def __init__(   self, 
                    scene, 
                    **kwargs ):

        """
        constructor
        """

        # initialise base object
        super().__init__( scene, **kwargs )

        # define norad ids
        self._norad_id = {  
                            'PHR1A' : 38012,
                            'PHR1B' : 39019,
                        }

        # get platform and tle
        self._platform = self.getPlatform( scene, r'_PHR[\d][A|B]_' )
        self._tle = self._norad_id [ self._platform ]

        return


    def processToArd( self ):

        """
        manage processing from raw dataset to ard
        """

        # create tmp working directory
        root_path = os.path.join( os.path.dirname( self._scene ), 'tmp' )

        path = os.path.join( root_path, 'scene' )
        if not os.path.exists( path ):
            os.makedirs( path )

        # extract dataset to tmp path
        out, err, code = ps.extractZip( self._scene, path )
        if code == 0:
        
            # get image list and corresponding srtm tiles
            images = self.getImageLists( path ); 
            self.getSrtmTiles( images[ 'P' ] )

            # panchromatic and multispectral image sets
            mosaic = {}
            for _id in self._image_ids:

                # generate calibration images
                out_path = os.path.join( root_path, 'cal/{}'.format( _id ) )
                cal_images = self.getCalibratedImages( images[ _id ], out_path, milli=True ) 

                # create mosaic 
                out_path = os.path.join( root_path, 'mosaic/{}'.format( _id ) )
                mosaic[ _id ] = self.getTileFusionImages( cal_images, out_path )

                # optionally grab roi into mosaic
                if self._roi is not None:                    
                    out_path = os.path.join( root_path, 'roi/{}'.format( _id ) )
                    mosaic[ _id ] = self.getRoiImage( mosaic[ _id ], out_path )

            # superimpose multispectral image on panchromatic geometry
            out_path = os.path.join( root_path, 'pan' )
            mosaic[ 'MS' ] = self.getSuperimposedImage( mosaic, out_path )

            # generate pansharpened image
            out_path = os.path.join( root_path, 'pan' )
            pan_image = self.getPansharpenImage( mosaic, out_path )


        # return pansharpened image and multispectral mosaic
        return pan_image, mosaic[ 'MS' ]

