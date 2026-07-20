import nibabel as nib
from fury import actor
from scipy.ndimage import gaussian_filter


### Glass brain actor:
def glass_actor(image, threshold=50, sigma=0.1, color=(0, 0, 0), opacity=0.04):
    """Return a 3D glass-brain contour actor from a NIfTI image or file path."""
    img = nib.load(image) if isinstance(image, str) else image
    data = img.get_fdata().copy()
    data[data < threshold] = 0
    data = gaussian_filter(data, sigma=sigma)
    return actor.contour_from_roi(data, affine=img.affine, color=color, opacity=opacity)


## Brain slice actor:
def brain_actor(brain_2d, opacity=0.9):
    """Return a 2D slicer actor from a NIfTI image or file path.
    """
    img = nib.load(brain_2d) if isinstance(brain_2d, str) else brain_2d
    data = img.get_fdata()
    nonzero = data[data > 0]
    if nonzero.size == 0:
        value_range = (data.min(), data.max())
    else:
        mu, sigma = nonzero.mean(), nonzero.std()
        sigma = sigma if sigma > 0 else 1.0
        value_range = (mu - 0.1 * sigma, mu + 3 * sigma)
    return actor.slicer(data, affine=img.affine, value_range=value_range, opacity=opacity)
