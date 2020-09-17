import os
from osgeo import gdal

import numpy as np
import numpy.ma as ma


class PCRasterWriter:
    FORMAT = 'PCRaster'
    dtype_to_valuescale = {
        'uint8': (gdal.GDT_Byte, 'VS_BOOLEAN'),
        'int8': (gdal.GDT_Int32, 'VS_NOMINAL'),
        'int16': (gdal.GDT_Int32, 'VS_ORDINAL'),
        'float32': (gdal.GDT_Float32, 'VS_SCALAR'),
        'float64': (gdal.GDT_Float32, 'VS_SCALAR'),
    }

    def __init__(self, *args, **kwargs):
        # TODO can be used without clonemap. It means we need to pass info to set GeoTransform
        # geo transform is a tuple e.g.  (2500000.0, 5000.0, 0.0, 5500000.0, 0.0, -5000.0)
        # 0 - xul
        # 1 - w-e pixel resolution
        # 2 - 0.0 (?)
        # 3 - yul
        # 4
        # 5 - n-s pixel resolution (negative value)
        # Xp = padfTransform[0] + P*padfTransform[1] + L*padfTransform[2];
        # Yp = padfTransform[3] + P*padfTransform[4] + L*padfTransform[5];
        self._clone_map = args[0]
        mv = kwargs.get('mv')
        # =============================================================================
        # Create a MEM clone of the source file.
        # =============================================================================

        self._drv = gdal.GetDriverByName(self.FORMAT)
        self._drv.Register()
        src_ds = gdal.Open(self._clone_map.encode('utf-8'), gdal.GA_ReadOnly)
        src_band = src_ds.GetRasterBand(1)

        # Producing mask array
        self.cols = src_ds.RasterXSize
        self.rows = src_ds.RasterYSize
        self.src_geo_transform = src_ds.GetGeoTransform()
        rs = src_band.ReadAsArray(0, 0, self.cols, self.rows)
        no_data_value = src_band.GetNoDataValue()
        src_band.DeleteNoDataValue()
        src_ds = None
        del src_ds
        src_band = None
        del src_band
        rs = ma.masked_values(rs, no_data_value, copy=False)
        self._mask = ma.getmask(rs)
        self.mv = no_data_value if not mv else float(mv)
        rs = None

    def write(self, output_map_name, values):
        etype, valuescale = self.get_valuescale(values)
        filled_values = self._mask_values(values, self.mv)
        filled_values = filled_values.astype(np.float32)
        dest_ds = self._drv.Create('temp.map', xsize=self.cols, ysize=self.rows, bands=1,
                                   eType=etype,
                                   options=["PCRASTER_VALUESCALE={}".format(valuescale)])
        mem_drive = gdal.GetDriverByName('MEM')
        mem_drive.Register()
        mem_ds = mem_drive.CreateCopy('mem', dest_ds)
        rs = mem_ds.GetRasterBand(1)
        rs.WriteArray(filled_values)
        mem_ds.SetGeoTransform(self.src_geo_transform)
        # FIXME this set missing value statement is ignored once file is written on disk
        rs.SetNoDataValue(self.mv)
        rs.FlushCache()

        out_ds = self._drv.CreateCopy(output_map_name.encode('utf-8'), mem_ds)
        out_ds = None
        del out_ds
        dest_ds = None
        del dest_ds
        mem_ds = None
        del mem_ds
        os.unlink('temp.map')

    def _mask_values(self, values, mv=None):
        if isinstance(values, ma.core.MaskedArray):
            masked = ma.masked_where((self._mask | values.mask), values.data, copy=False)
        else:
            masked = ma.masked_where(self._mask, values, copy=False)
        mv = self.mv if not mv else mv
        masked = ma.filled(masked, mv)
        return masked

    def close(self):
        pass

    def get_valuescale(self, values):
        dtype = str(values.dtype)
        return self.dtype_to_valuescale[dtype]
