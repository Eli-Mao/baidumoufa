"""Frozen EOP and independent SOFA/ERFA Earth orientation for STK 11.6.

ICRF uses IAU 2006/2000A with observed/predicted dX,dY. STK's J2000
definition uses the uncorrected IAU 1976/1980 theory, UT1, and polar motion.
Positions are km. EOP angular columns are arcseconds; no network downloads.
"""
from pathlib import Path
import hashlib
import numpy as np
import erfa
from scipy.interpolate import CubicSpline
from sso import STK_MU,STK_RE_J2,STK_J2

DEFAULT_EOP = Path(__file__).resolve().parent/'data/earth_orientation/EOP-20261105.txt'
DAY = 86400.
ARCSEC = np.pi/(180*3600)
WGS84_A = 6378.137
WGS84_B = WGS84_A*(1-1/298.257223563)
AXES = np.array([WGS84_A, WGS84_A, WGS84_B])


def geodetic_xyz(lon_deg, lat_deg, height_km=0.):
    lon, lat, h = np.broadcast_arrays(np.radians(lon_deg), np.radians(lat_deg), height_km)
    e2 = 1-(WGS84_B/WGS84_A)**2
    n = WGS84_A/np.sqrt(1-e2*np.sin(lat)**2)
    return np.stack(((n+h)*np.cos(lat)*np.cos(lon), (n+h)*np.cos(lat)*np.sin(lon),
                     (n*(1-e2)+h)*np.sin(lat)), axis=-1)


def rz(angle):
    c, s = np.cos(angle), np.sin(angle)
    out = np.zeros(np.shape(angle)+(3,3))
    out[...,0,0]=c; out[...,0,1]=s
    out[...,1,0]=-s; out[...,1,1]=c; out[...,2,2]=1
    return out


class EarthFrames:
    def __init__(self, jd0=2461406.5, duration_s=604800., eop_path=DEFAULT_EOP):
        self.jd0, self.duration_s = float(jd0), float(duration_s)
        self.path = Path(eop_path)
        raw = self.path.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        rows = []
        for line in raw.decode('ascii').splitlines():
            cols = line.split()
            if len(cols)==13 and cols[0].isdigit() and len(cols[0])==4:
                rows.append([float(x) for x in cols])
        self.eop = np.asarray(rows)
        if self.eop.ndim != 2 or not np.isfinite(self.eop).all() or np.any(np.diff(self.eop[:,3])!=1):
            raise ValueError('EOP must contain unique consecutive finite daily records')
        self.mjd0 = self.jd0-2400000.5
        self.values(np.array([0., duration_s]))
        # Smooth celestial orientation changes very slowly; interpolate only
        # that matrix, never the rapidly rotating terrestrial frame.
        ts = np.arange(-600., duration_s+1200., 600.)
        # Padding must also be backed by actual frozen EOP records.
        e = self.values(ts)
        tt = (self.mjd0+ts/DAY)+(e[:,12]+32.184)/DAY
        x,y,s = erfa.xys06a(2400000.5,tt)
        x += e[:,10]*ARCSEC; y += e[:,11]*ARCSEC
        self._cio = CubicSpline(ts, erfa.c2ixys(x,y,s), axis=0, extrapolate=False)

    def values(self, times_s):
        t = np.asarray(times_s, float)
        if not np.isfinite(t).all(): raise ValueError('nonfinite time')
        mjd = self.mjd0+t/DAY
        if np.any(mjd<self.eop[0,3]) or np.any(mjd>self.eop[-1,3]):
            raise ValueError('frozen EOP does not cover requested dates')
        return np.stack([np.interp(mjd,self.eop[:,3],self.eop[:,k]) for k in range(13)],axis=-1)

    def matrix(self, times_s, source='ICRF'):
        t = np.asarray(times_s, float)
        e = self.values(t)
        utc = self.mjd0+t/DAY
        tt = utc+(e[...,12]+32.184)/DAY
        ut1 = utc+e[...,6]/DAY
        pm = erfa.pom00(e[...,4]*ARCSEC,e[...,5]*ARCSEC,erfa.sp00(2400000.5,tt))
        if source=='ICRF':
            ci = self._cio(t)
            if not np.isfinite(ci).all(): raise ValueError('time outside frame interpolation span')
            return pm @ rz(erfa.era00(2400000.5,ut1)) @ ci
        if source!='J2000': raise ValueError('source must be ICRF or J2000')
        dp,de = erfa.nut80(2400000.5,tt)
        # STK's FK5 J2000 definition uses theoretical (uncorrected) nutation.
        # Applying dPsi/dEps here would nearly collapse J2000 onto ICRF and
        # introduce a metre-scale initial-state rotation error.
        eps = erfa.obl80(2400000.5,tt)
        pn = erfa.numat(eps,dp,de) @ erfa.pmat76(2400000.5,tt)
        gast = erfa.gmst82(2400000.5,ut1)+erfa.eqeq94(2400000.5,tt)
        return pm @ rz(gast) @ pn

    def j2000_to_icrf(self, times_s):
        return np.swapaxes(self.matrix(times_s,'ICRF'),-1,-2) @ self.matrix(times_s,'J2000')

    def fixed_state(self, r, v, times_s):
        t=np.asarray(times_s,float)
        m=self.matrix(t)
        dm=(self.matrix(t+.5)-self.matrix(t-.5))
        return (np.einsum('...ij,...j->...i',m,r),
                np.einsum('...ij,...j->...i',m,v)+np.einsum('...ij,...j->...i',dm,r))


class StkOrbit:
    """Native J2 secular equations in ICRF, from mean J2000 circular elements.

    Gravity constants are the installed STK 11.6 EGM2008 model, not WGS84 GM.
    This class has no dependency on STK or exported spacecraft trajectories.
    """
    MU=STK_MU
    RE=STK_RE_J2
    # Read from the native satellite's "Gravity Model" data provider. STK's
    # runtime value differs from directly unnormalizing the disk C20 entry.
    J2=STK_J2

    def __init__(self, element, frames):
        self.frames=frames
        self.a=6371.+float(element.alt_km)
        i,O,u=np.radians([element.inc_deg,element.raan_deg,element.u_deg])
        p=np.array([np.cos(O),np.sin(O),0.])
        q=np.array([-np.sin(O)*np.cos(i),np.cos(O)*np.cos(i),np.sin(i)])
        rot=frames.j2000_to_icrf(0.)
        pp,qq=rot@p,rot@q
        normal=np.cross(pp,qq)
        inc=np.arccos(np.clip(normal[2],-1,1))
        node=np.arctan2(normal[0],-normal[1])
        self.p=np.array([np.cos(node),np.sin(node),0.])
        self.q=np.cross(normal,self.p)
        radius=np.cos(u)*pp+np.sin(u)*qq
        self.u0=np.arctan2(radius@self.q,radius@self.p)
        n=np.sqrt(self.MU/self.a**3)
        self.n=n
        k=self.J2*(self.RE/self.a)**2
        md=n*(1+.75*k*(3*np.cos(inc)**2-1))
        self.rd=-1.5*k*md*np.cos(inc)
        self.ud=md+.75*k*md*(5*np.cos(inc)**2-1)

    def inertial(self,times_s,velocity_mode='stk'):
        t=np.atleast_1d(np.asarray(times_s,float))
        u=self.u0+self.ud*t
        r0=self.a*(np.cos(u)[:,None]*self.p+np.sin(u)[:,None]*self.q)
        speed=self.n if velocity_mode=='stk' else self.ud
        if velocity_mode not in ('stk','derivative'): raise ValueError('invalid velocity mode')
        v0=self.a*speed*(-np.sin(u)[:,None]*self.p+np.cos(u)[:,None]*self.q)
        spin=rz(-self.rd*t)
        r=np.einsum('tij,tj->ti',spin,r0)
        v=np.einsum('tij,tj->ti',spin,v0)
        if velocity_mode=='derivative': v+=self.rd*np.cross(np.array([0.,0.,1.]),r)
        return r,v

    def state(self,times_s):
        return self.frames.fixed_state(*self.inertial(times_s),np.atleast_1d(times_s))
