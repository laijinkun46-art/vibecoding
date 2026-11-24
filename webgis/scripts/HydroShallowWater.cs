// 教学用二维浅水方程：面通量 + 静水重构 + 半隐式 Manning 摩阻。
// Net flux is counted on the exact numerical boundary faces used in the update.
using System;
using System.IO;
using System.Globalization;

public static class HydroShallowWater
{
    const double G = 9.81, Dry = 0.003;
    struct Cell { public double z, n, area, h, x, y, dh, dx, dy, perimeter; }
    struct Face { public int l, r, type; public double len, nx, ny; }
    static double[] times, inlet, stages;
    static double areaW, lateralThreshold, lateralSlope, lateralN;
    static Cell[] c;
    static Face[] faces;
    static double inW, outE, outSide, added;
    static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    static double Curve(double[] values, double t)
    {
        int i=0, hi=times.Length-1;
        while (hi-i>1) {
            int mid=(i+hi)/2;
            if(t>=times[mid]) i=mid; else hi=mid;
        }
        double u=Math.Max(0,Math.Min(1,(t-times[i])/(times[i+1]-times[i])));
        return values[i]+(values[i+1]-values[i])*u;
    }

    static void Flux(Face f, double westSpeed, double eastStage, double dt)
    {
        int l=f.l,r=f.r;
        double h=c[l].h, z=c[l].z, nx=f.nx, ny=f.ny, len=f.len;
        double ux=h>Dry?c[l].x/h:0, uy=h>Dry?c[l].y/h:0;
        double un=ux*nx+uy*ny, vn=-ux*ny+uy*nx;
        double hr=h,zr=z,ur=-un,vr=vn;
        if(r>=0) {
            hr=c[r].h; zr=c[r].z;
            double vx=hr>Dry?c[r].x/hr:0, vy=hr>Dry?c[r].y/hr:0;
            ur=vx*nx+vy*ny; vr=-vx*ny+vy*nx;
        } else if(f.type==2) {
            hr=Math.Max(0,eastStage-z); ur=un; vr=0;
        } else if(f.type==1 || (f.type==3 && h>=lateralThreshold)) {
            double q=f.type==1 ? -westSpeed*h : Math.Min(h*Math.Sqrt(G*h),
                Math.Pow(h,5.0/3.0)*Math.Sqrt(lateralSlope)/lateralN);
            double normalMomentum=.5*G*h*h+(h>Dry?q*q/h:0);
            c[l].dh-=len*q;
            c[l].dx-=len*(normalMomentum*nx-q*vn*ny);
            c[l].dy-=len*(normalMomentum*ny+q*vn*nx);
            if(f.type==1) inW-=q*len*dt; else outSide+=q*len*dt;
            return;
        }
        if(h<1e-10 && hr<1e-10) return;
        double cut=Math.Max(z,zr);
        double a=Math.Max(0,h+z-cut), b=Math.Max(0,hr+zr-cut);
        double wave=Math.Max(Math.Abs(un)+Math.Sqrt(G*a),Math.Abs(ur)+Math.Sqrt(G*b));
        double f0=.5*(a*un+b*ur-wave*(b-a));
        double fn=.5*(a*un*un+b*ur*ur+.5*G*(a*a+b*b)-wave*(b*ur-a*un));
        double ft=.5*(a*un*vn+b*ur*vr-wave*(b*vr-a*vn));
        double fl=fn+.5*G*(h*h-a*a);
        c[l].dh-=len*f0;
        c[l].dx-=len*(fl*nx-ft*ny);
        c[l].dy-=len*(fl*ny+ft*nx);
        if(r>=0) {
            double fr=fn+.5*G*(hr*hr-b*b);
            c[r].dh+=len*f0;
            c[r].dx+=len*(fr*nx-ft*ny);
            c[r].dy+=len*(fr*ny+ft*nx);
        } else if(f.type==2) outE+=f0*len*dt;
    }

    static double Volume()
    {
        double v=0;
        for(int i=0;i<c.Length;i++) v+=c[i].h*c[i].area;
        return v;
    }

    static void Main(string[] args)
    {
        double duration, interval;
        using(var b=new BinaryReader(File.OpenRead(args[0]))) {
            int count=b.ReadInt32(), nf=b.ReadInt32(), nk=b.ReadInt32();
            duration=b.ReadDouble(); interval=b.ReadDouble();
            lateralThreshold=b.ReadDouble(); lateralSlope=b.ReadDouble(); lateralN=b.ReadDouble();
            c=new Cell[count]; faces=new Face[nf];
            times=new double[nk]; inlet=new double[nk]; stages=new double[nk];
            for(int i=0;i<nk;i++) { times[i]=b.ReadDouble(); inlet[i]=b.ReadDouble(); stages[i]=b.ReadDouble(); }
            for(int i=0;i<count;i++) {
                c[i].z=b.ReadDouble(); c[i].n=b.ReadDouble(); c[i].area=b.ReadDouble();
                c[i].h=b.ReadDouble(); c[i].x=b.ReadDouble(); c[i].y=b.ReadDouble();
            }
            for(int i=0;i<nf;i++) {
                Face f=new Face {l=b.ReadInt32(),r=b.ReadInt32(),type=b.ReadInt32(),len=b.ReadDouble(),nx=b.ReadDouble(),ny=b.ReadDouble()};
                faces[i]=f; c[f.l].perimeter+=f.len;
                if(f.r>=0) c[f.r].perimeter+=f.len;
            }
            if(b.BaseStream.Position!=b.BaseStream.Length) throw new InvalidDataException("mesh trailing bytes");
        }
        double t=0, initial=Volume(), maxSpeed=0, minRawDepth=0;
        int frame=0, steps=0;
        using(var budget=new StreamWriter(Path.Combine(args[1],"budget.csv"))) {
            budget.WriteLine("index,t_seconds,volume_m3,inlet_m3,east_m3,lateral_m3,correction_m3,max_speed_mps,min_raw_depth_m,steps");
            for(;;) {
                double stop=Math.Min(frame*interval,duration);
                while(t<stop-1e-7) {
                    double dt=Math.Min(12,stop-t);
                    areaW=0;
                    for(int i=0;i<c.Length;i++) {
                        double h=c[i].h;
                        double speed=h>Dry?Math.Sqrt(c[i].x*c[i].x+c[i].y*c[i].y)/h:0;
                        double wave=speed+Math.Sqrt(G*h);
                        if(wave>0) dt=Math.Min(dt,1.28*c[i].area/(c[i].perimeter*wave));
                        c[i].dh=c[i].dx=c[i].dy=0;
                    }
                    for(int i=0;i<faces.Length;i++)
                        if(faces[i].type==1) areaW+=faces[i].len*c[faces[i].l].h;
                    double q=Curve(inlet,t+dt/2);
                    if(q>0 && areaW<1) throw new Exception("inlet is dry at "+t);
                    double westSpeed=areaW>0?q/areaW:0, eastStage=Curve(stages,t+dt/2);
                    if(!(dt>.00001) || westSpeed>16) throw new Exception("unstable boundary/CFL at "+t);
                    for(int i=0;i<faces.Length;i++) Flux(faces[i],westSpeed,eastStage,dt);
                    for(int i=0;i<c.Length;i++) {
                        double k=dt/c[i].area, h=c[i].h+k*c[i].dh;
                        if(Double.IsNaN(h) || Double.IsInfinity(h) || h<-.000001)
                            throw new Exception("invalid depth t="+t+" cell="+i+" h="+h);
                        minRawDepth=Math.Min(minRawDepth,h);
                        if(h<0) { added-=h*c[i].area; h=0; }
                        c[i].h=h;
                        if(h<=Dry) { c[i].x=c[i].y=0; continue; }
                        double x=c[i].x+k*c[i].dx, y=c[i].y+k*c[i].dy;
                        double speed=Math.Sqrt(x*x+y*y)/h;
                        double n=c[i].n;
                        double drag=1+dt*G*n*n*speed/Math.Pow(h,4.0/3.0);
                        c[i].x=x/drag; c[i].y=y/drag;
                        speed/=drag;
                        if(Double.IsNaN(speed) || speed>30) throw new Exception("invalid speed t="+t);
                        maxSpeed=Math.Max(maxSpeed,speed);
                    }
                    steps++; t+=dt;
                }
                using(var b=new BinaryWriter(File.Create(Path.Combine(args[1],frame.ToString("D4")+".f64"))))
                    for(int i=0;i<c.Length;i++) { b.Write(c[i].h); b.Write(c[i].x); b.Write(c[i].y); }
                budget.WriteLine(String.Format(Inv,"{0},{1:R},{2:R},{3:R},{4:R},{5:R},{6:R},{7:R},{8:R},{9}",
                    frame,stop,Volume(),inW,outE,outSide,added,maxSpeed,minRawDepth,steps));
                budget.Flush();
                if(frame%4==0) Console.WriteLine("frame {0} t={1:F0}s cells={2} steps={3} V={4:F0} residual={5:F4}",
                    frame,stop,c.Length,steps,Volume(),Volume()-initial-inW+outE+outSide-added);
                if(stop>=duration-1e-7) break;
                frame++;
            }
        }
    }
}
