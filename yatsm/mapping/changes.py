""" Functions relevant for mapping abrupt changes
"""
from datetime import datetime as dt
import logging

import numpy as np

logger = logging.getLogger(__name__)


# TODO: make these into 'transforms' sorts of functions


def get_change_date(start, end, result_location, image_ds,
                    first=False,
                    out_format='%Y%j',
                    magnitude=False,
                    ndv=-9999, pattern='yatsm_r*', warn_on_empty=False):
    """ Output raster with changemap

    Args:
        start (int): Ordinal date for start of map records
        end (int): Ordinal date for end of map records
        result_location (str): Location of results
        image_ds (gdal.Dataset): Example dataset
        first (bool): Use first change instead of last
        out_format (str, optional): Output date format
        magnitude (bool, optional): output magnitude of each change?
        ndv (int, optional): NoDataValue
        pattern (str, optional): filename pattern of saved record results
        warn_on_empty (bool, optional): Log warning if result contained no
            result records (default: False)


    Returns:
        tuple: A 2D np.ndarray array containing the changes between the
            start and end date. Also includes, if specified, a 3D np.ndarray of
            the magnitude of each change plus the indices of these magnitudes

    """
    # Find results
    records = find_results(result_location, pattern)

    logger.debug('Allocating memory...')
    datemap = np.ones((image_ds.RasterYSize, image_ds.RasterXSize),
                      dtype=np.int32) * int(ndv)
    # Determine what magnitude information to output if requested
    if magnitude:
        magnitude_indices = get_magnitude_indices(records)
        magnitudemap = np.ones((image_ds.RasterYSize, image_ds.RasterXSize,
                                magnitude_indices.size),
                               dtype=np.float32) * float(ndv)

    logger.debug('Processing results')
    for rec in iter_records(records, warn_on_empty=warn_on_empty):

        index = np.where((rec['break'] >= start) &
                         (rec['break'] <= end))[0]

        if first:
            _, _index = np.unique(rec['px'][index], return_index=True)
            index = index[_index]

        if index.shape[0] != 0:
            if out_format != 'ordinal':
                dates = np.array([int(dt.fromordinal(_d).strftime(out_format))
                                  for _d in rec['break'][index]])
                datemap[rec['py'][index], rec['px'][index]] = dates
            else:
                datemap[rec['py'][index], rec['px'][index]] = \
                    rec['break'][index]
            if magnitude:
                magnitudemap[rec['py'][index], rec['px'][index], :] = \
                    rec[index]['magnitude'][:, magnitude_indices]

    if magnitude:
        return datemap, magnitudemap, magnitude_indices
    else:
        return datemap, None, None


def get_change_num(start, end, result_location, image_ds,
                   ndv=-9999, pattern='yatsm_r*', warn_on_empty=False):
    """ Output raster with changemap

    Args:
        start (int): Ordinal date for start of map records
        end (int): Ordinal date for end of map records
        result_location (str): Location of results
        image_ds (gdal.Dataset): Example dataset
        ndv (int, optional): NoDataValue
        pattern (str, optional): filename pattern of saved record results
        warn_on_empty (bool, optional): Log warning if result contained no
            result records (default: False)

    Returns:
        np.ndarray: 2D numpy array containing the number of changes
            between the start and end date; list containing band names

    """
    # Find results
    records = find_results(result_location, pattern)

    logger.debug('Allocating memory...')
    raster = np.ones((image_ds.RasterYSize, image_ds.RasterXSize),
                     dtype=np.int32) * int(ndv)

    logger.debug('Processing results')
    for rec in iter_records(records, warn_on_empty=warn_on_empty):
        # Find all changes in time period
        changed = (rec['break'] >= start) & (rec['break'] <= end)
        # Use raveled index to get unique x/y positions
        idx_changed = np.ravel_multi_index(
            (rec['py'][changed], rec['px'][changed]),
            raster.shape
        )
        # Now possible in numpy>=1.9 -- return counts of unique indices
        idx_uniq, idx_count = np.unique(idx_changed, return_counts=True)
        # Add in the values
        py, px = np.unravel_index(idx_uniq, raster.shape)
        raster[py, px] = idx_count

    return raster
