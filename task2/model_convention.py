"""One scoped J2 convention shared by design, propagation and validation.

New work defaults to STK. Historic inputs can be identified from their SSO
inclination, or selected explicitly as first_order. Contexts restore on exit
and do not leak across asynchronous tasks or independently created evaluators.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import os
from functools import wraps

MODELS=('stk','first_order')
DEFAULT_RATE_MODEL=os.environ.get('TASK2_RATE_MODEL','stk')
if DEFAULT_RATE_MODEL not in MODELS:raise ValueError('invalid TASK2_RATE_MODEL')
_active=ContextVar('task2_rate_model',default=DEFAULT_RATE_MODEL)


def rate_model(value=None):
    selected=_active.get() if value is None else value
    if selected not in MODELS:raise ValueError(f'unknown J2 rate model: {selected}')
    return selected


@contextmanager
def using_rate_model(value):
    token=_active.set(rate_model(value))
    try:yield
    finally:_active.reset(token)


def scoped_method(method):
    @wraps(method)
    def call(self,*args,**kwargs):
        with using_rate_model(self.rate_model):return method(self,*args,**kwargs)
    return call


def element_model(elems,requested='auto',tolerance_deg=1e-5):
    """Resolve a design convention, rejecting mixed or unidentified SSO designs."""
    import numpy as np
    from sso import design_inclination
    if requested not in (None,'auto'):return rate_model(requested)
    alt=elems['alt_km'] if 'alt_km' in elems else elems['h_km']
    fits=[]
    for model in MODELS:
        error=np.asarray(elems.inc_deg)-design_inclination(np.asarray(alt),np.asarray(elems.raan_deg),rate_model=model)
        if len(error) and np.isfinite(error).all() and np.max(abs(error))<=tolerance_deg:fits.append(model)
    if len(fits)!=1:raise ValueError('SSO convention is mixed or unidentified; specify and validate --rate-model')
    return fits[0]
