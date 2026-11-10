"""Independent WGS84 point and continuous-region rectangular sensor geometry."""
import numpy as np
from continuous_region import SphericalRegion, _camera
from earth_frames import AXES, WGS84_B, geodetic_xyz


def point_margin(r,v,p,half_deg=.81):
    """Positive inside both FOV planes and the visible WGS84 hemisphere, km.

    r/v/p have matching or broadcastable (...,3) shapes. Nadir is geocentric;
    attitude uses native J2's Keplerian velocity rotated to Earth Fixed.
    """
    r,v,p=np.broadcast_arrays(np.asarray(r,float),np.asarray(v,float),np.asarray(p,float))
    up=r/np.linalg.norm(r,axis=-1,keepdims=True)
    along=v-np.sum(v*up,axis=-1,keepdims=True)*up
    along/=np.linalg.norm(along,axis=-1,keepdims=True)
    cross=np.cross(up,along)
    ray=p-r
    z=-np.sum(ray*up,axis=-1)
    tan=np.tan(np.radians(half_deg))
    m=np.minimum(tan*z-np.abs(np.sum(ray*along,axis=-1)),tan*z-np.abs(np.sum(ray*cross,axis=-1)))
    visible=np.sum((r-p)*(p/AXES**2),axis=-1)>=0
    return np.where((z>0)&visible,m,-np.abs(m)-1.)


class EllipsoidRegion(SphericalRegion):
    """Ellipsoid surface intersection after affine mapping to the unit sphere.

    Edges are minor central-plane great arcs through the WGS84 boundary points.
    Sensor-plane intersections are analytic, without region evaluation grids.
    """
    def __init__(self,rings):
        transformed=[]
        for ring in rings:
            ring=np.asarray(ring,float)
            q=geodetic_xyz(ring[:,0],ring[:,1])/AXES
            transformed.append(np.column_stack((np.degrees(np.arctan2(q[:,1],q[:,0])),
                                               np.degrees(np.arctan2(q[:,2],np.hypot(q[:,0],q[:,1]))))))
        super().__init__(transformed)
        self.original_lonlat=[np.asarray(r,float) for r in rings]
        self.physical_vertices=self.vertices*AXES

    def intersects(self,r,v,along_half_deg=.81,cross_half_deg=.81):
        r,v=np.atleast_2d(r),np.atleast_2d(v)
        if r.shape!=v.shape or r.shape[-1]!=3 or not np.isfinite(r).all() or not np.isfinite(v).all():
            raise ValueError('matching finite position and velocity required')
        rho,up,along,cross=_camera(r,v)
        qpos=r/AXES
        qpos/=np.linalg.norm(qpos,axis=1)[:,None]
        ta,tc=np.tan(np.radians([along_half_deg,cross_half_deg]))
        if not 0<min(along_half_deg,cross_half_deg)<=max(along_half_deg,cross_half_deg)<90:
            raise ValueError('invalid half angles')
        eta=np.arctan(np.hypot(ta,tc))
        arg=rho/WGS84_B*np.sin(eta)
        if np.any(rho<=AXES.max()) or np.any(arg>=1): raise ValueError('unsupported orbit/FOV beyond limb')
        cap=(np.arcsin(arg)-eta)*1.02+.00001
        hit=self.contains(qpos)
        pending=np.flatnonzero(~hit)
        vertices=self.physical_vertices
        for begin in range(0,len(pending),512):
            ids=pending[begin:begin+512]
            z=rho[ids,None]-up[ids]@vertices.T
            good=np.any((np.abs(along[ids]@vertices.T)<=ta*z+1e-9)&
                        (np.abs(cross[ids]@vertices.T)<=tc*z+1e-9)&
                        (r[ids]@(vertices/AXES**2).T>=1),axis=1)
            hit[ids[good]]=True
            ids=ids[~good]
            if not len(ids): continue
            ua,uq=qpos[ids]@self.a.T,qpos[ids]@self.q.T
            theta=np.arctan2(uq,ua)
            maxdot=np.maximum(ua,qpos[ids]@self.b.T)
            maxdot=np.where((theta>=0)&(theta<=self.alpha),np.maximum(maxdot,np.hypot(ua,uq)),maxdot)
            sample,edge=np.nonzero(maxdot>=np.cos(cap[ids,None])-1e-12)
            ti=ids[sample]
            if not len(ti): continue
            a,q,alpha=self.a[edge]*AXES,self.q[edge]*AXES,self.alpha[edge]
            for axis,tan in ((along,ta),(cross,tc)):
                for sign in (-1,1):
                    plane=sign*axis[ti]-tan*up[ti]
                    aa=np.sum(plane*a,axis=1);bb=np.sum(plane*q,axis=1);cc=tan*rho[ti]
                    amp=np.hypot(aa,bb);phase=np.arctan2(bb,aa)
                    angle=np.arccos(np.clip(-cc/np.maximum(amp,1e-30),-1,1))
                    for branch in (-1,1):
                        root=(phase+branch*angle)%(2*np.pi)
                        root=np.where(np.abs(root-2*np.pi)<1e-10,0,root)
                        valid=(amp>=abs(cc)-1e-9)&(root<=alpha+1e-10)
                        if not valid.any(): continue
                        jj=ti[valid];tt=root[valid]
                        p=a[valid]*np.cos(tt)[:,None]+q[valid]*np.sin(tt)[:,None]
                        zz=rho[jj]-np.sum(p*up[jj],axis=1)
                        okay=((np.sum(r[jj]*(p/AXES**2),axis=1)>=1-1e-12)&
                              (np.abs(np.sum(p*along[jj],axis=1))<=ta*zz+1e-7)&
                              (np.abs(np.sum(p*cross[jj],axis=1))<=tc*zz+1e-7))
                        hit[jj[okay]]=True
        return hit
