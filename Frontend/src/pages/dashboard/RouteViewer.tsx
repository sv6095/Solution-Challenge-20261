import { useRef, useEffect, useMemo, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Plane, Clock, DollarSign, MapPin, Navigation, Clock3, Truck, UserRound } from "lucide-react";
import { Map, MapRoute, MapControls, MapMarker, MarkerContent, MarkerTooltip, type MapRef } from "@/components/ui/map";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/* ── Types ─────────────────────────────────────────────────────────── */
type AP = { icao: string; iata: string; name: string; city: string; country: string; lat: number; lon: number; elevation?: number };
type RouteOption = { label: string; legs: AP[]; distKm: number; hours: number; color: string; dash?: [number,number] };

interface OsrmRouteData {
  coordinates: [number, number][];
  duration: number;
  distance: number;
}

/* ── Haversine (ports project1.py distance()) ───────────────────────── */
function hav(a: AP, b: AP) {
  const R = 6371, r = Math.PI / 180;
  const dLat = (b.lat - a.lat) * r, dLon = (b.lon - a.lon) * r;
  const x = Math.sin(dLat/2)**2 + Math.cos(a.lat*r)*Math.cos(b.lat*r)*Math.sin(dLon/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1-x));
}

/* ── Great-circle arc for MapRoute ─────────────────────────────────── */
function arc(from: AP, to: AP, steps = 80): [number,number][] {
  const r = Math.PI/180, d = 180/Math.PI;
  const [lo1,la1,lo2,la2] = [from.lon*r, from.lat*r, to.lon*r, to.lat*r];
  
  // Calculate central angle Omega
  let cosOmega = Math.sin(la1)*Math.sin(la2) + Math.cos(la1)*Math.cos(la2)*Math.cos(lo1-lo2);
  // Clamp to avoid precision errors
  cosOmega = Math.max(-1, Math.min(1, cosOmega));
  const Omega = Math.acos(cosOmega);
  
  // If points are same or antipodal, fallback to straight line
  if (Omega === 0 || Math.abs(Omega - Math.PI) < 1e-6) {
    return [[from.lon, from.lat], [to.lon, to.lat]];
  }

  const sinOmega = Math.sin(Omega);
  let prevLon: number | null = null;
  let lonOffset = 0;

  return Array.from({length:steps+1},(_,i)=>{
    const f=i/steps;
    const A = Math.sin((1-f)*Omega)/sinOmega;
    const B = Math.sin(f*Omega)/sinOmega;
    
    const x=A*Math.cos(la1)*Math.cos(lo1)+B*Math.cos(la2)*Math.cos(lo2);
    const y=A*Math.cos(la1)*Math.sin(lo1)+B*Math.cos(la2)*Math.sin(lo2);
    const z=A*Math.sin(la1)+B*Math.sin(la2);
    
    let lat = Math.atan2(z,Math.sqrt(x*x+y*y))*d;
    let lon = Math.atan2(y,x)*d;
    
    // Antimeridian crossing fix
    if (prevLon !== null) {
      const diff = lon - prevLon;
      if (diff > 180) lonOffset -= 360;
      else if (diff < -180) lonOffset += 360;
    }
    prevLon = lon;
    
    return [lon + lonOffset, lat] as [number,number];
  });
}

/* ── Utilities ───────────────────────────────────────────────────────── */
function formatDistance(meters?: number) {
  if (!meters) return "--";
  if (meters < 1000) return `${Math.round(meters)} m`;
  return `${(meters / 1000).toFixed(1)} km`;
}

function formatDuration(seconds?: number) {
  if (!seconds) return "--";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

/* ── Hub hubs (from project1.py: Dubai, Singapore, New York, Beijing) ─ */
const HUB_IATA = ["DXB","SIN","JFK","PEK"];
const STUB: Record<string,AP> = {
  DXB:{icao:"OMDB",iata:"DXB",name:"Dubai Intl",city:"Dubai",country:"AE",lat:25.252,lon:55.364},
  SIN:{icao:"WSSS",iata:"SIN",name:"Changi",city:"Singapore",country:"SG",lat:1.360,lon:103.989},
  JFK:{icao:"KJFK",iata:"JFK",name:"JFK Intl",city:"New York",country:"US",lat:40.639,lon:-73.779},
  PEK:{icao:"ZBAA",iata:"PEK",name:"Capital Intl",city:"Beijing",country:"CN",lat:40.080,lon:116.584},
  HKG:{icao:"VHHH",iata:"HKG",name:"Hong Kong Intl",city:"Hong Kong",country:"HK",lat:22.308,lon:113.915},
  LHR:{icao:"EGLL",iata:"LHR",name:"Heathrow",city:"London",country:"GB",lat:51.477,lon:-0.461},
  FRA:{icao:"EDDF",iata:"FRA",name:"Frankfurt",city:"Frankfurt",country:"DE",lat:50.033,lon:8.570},
  ORD:{icao:"KORD",iata:"ORD",name:"O'Hare Intl",city:"Chicago",country:"US",lat:41.978,lon:-87.904},
  BOM:{icao:"VABB",iata:"BOM",name:"Chhatrapati Shivaji",city:"Mumbai",country:"IN",lat:19.089,lon:72.868},
  SYD:{icao:"YSSY",iata:"SYD",name:"Kingsford Smith",city:"Sydney",country:"AU",lat:-33.947,lon:151.179},
};

const ROUTE_COLORS = ["#dc2626","#2563eb","#16a34a","#d97706","#7c3aed"];

function computeRoutes(from: AP, to: AP, hubs: AP[]): RouteOption[] {
  const AIR_KMH = 900;
  const direct = hav(from, to);

  const routes: RouteOption[] = [];
  routes.push({
    label: "Direct",
    legs: [from, to],
    distKm: direct,
    hours: direct / AIR_KMH,
    color: ROUTE_COLORS[0],
  });

  hubs.forEach((hub, i) => {
    if (hub.iata === from.iata || hub.iata === to.iata) return;
    const via = hav(from, hub) + hav(hub, to);
    routes.push({
      label: `Via ${hub.city}`,
      legs: [from, hub, to],
      distKm: via,
      hours: via / AIR_KMH + 1.5, // 1.5h layover
      color: ROUTE_COLORS[i+1] || "#6b7280",
      dash: [8,5],
    });
  });

  routes.sort((a,b) => a.distKm - b.distKm);
  return routes;
}


/* ── Components ─────────────────────────────────────────────────────── */

function LandRouteViewer({ fromAP, toAP, incTitle }: { fromAP: AP, toAP: AP, incTitle: string }) {
  const navigate = useNavigate();
  const [routeData, setRouteData] = useState<OsrmRouteData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchRoute() {
      setLoading(true);
      try {
        const response = await fetch(
          `https://router.project-osrm.org/route/v1/driving/${fromAP.lon},${fromAP.lat};${toAP.lon},${toAP.lat}?overview=full&geometries=geojson`,
        );
        const data = await response.json();
        const route = data?.routes?.[0];
        if (!route?.geometry?.coordinates) return;

        setRouteData({
          coordinates: route.geometry.coordinates as [number, number][],
          duration: route.duration as number,
          distance: route.distance as number,
        });
      } catch (error) {
        console.error("Failed to fetch route:", error);
      } finally {
        setLoading(false);
      }
    }

    // Only fetch if distance is reasonable or they are different
    if (fromAP.lon !== toAP.lon) fetchRoute();
    else setLoading(false);
  }, [fromAP, toAP]);

  const progressCoordinates = useMemo(() => {
    return routeData?.coordinates?.slice(0, 1) ?? [];
  }, [routeData]);

  const courierPosition = progressCoordinates[progressCoordinates.length - 1];
  const mapRef = useRef<MapRef>(null);

  useEffect(() => {
    mapRef.current?.easeTo({ pitch: 60, duration: 500 });
  }, []);

  const distKm = (routeData?.distance || hav(fromAP, toAP) * 1000) / 1000;
  const zoom = distKm > 8000 ? 2 : distKm > 4000 ? 2.8 : distKm > 2000 ? 3.8 : distKm > 500 ? 5 : 7;

  return (
    <div className="p-8 h-[calc(100vh-120px)] bg-slate-50 overflow-y-auto font-sans">
      <button onClick={()=>navigate(-1)} className="mb-4 flex items-center gap-2 text-xs font-mono font-bold uppercase tracking-wider text-slate-500 hover:text-slate-700 bg-white border border-slate-200 rounded-md px-3 py-1.5 cursor-pointer shadow-sm">
        <ArrowLeft size={13}/> Back
      </button>

      <div className="bg-white mx-auto grid max-w-7xl rounded-xl border border-slate-200 shadow-sm md:h-[600px] md:grid-cols-[1.05fr_1fr] overflow-hidden">
        <div className="flex flex-col p-5 md:p-6 overflow-y-auto">
          <div className="space-y-1">
            <h3 className="text-2xl font-semibold tracking-tight text-slate-900">
              Track Freight
            </h3>
            <p className="text-sm text-slate-500">Incident: {incTitle}</p>
          </div>

          <Card className="mt-5 shadow-none border-slate-200">
            <CardHeader className="pb-4">
              <CardTitle className="font-medium text-slate-800 text-lg">
                Route summary
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between text-sm border border-slate-100 rounded-md px-4 py-2.5 bg-slate-50">
                <span className="text-slate-500 font-medium">Distance</span>
                <span className="font-bold text-slate-800">{formatDistance(routeData?.distance || distKm * 1000)}</span>
              </div>
              <div className="flex items-center justify-between text-sm border border-slate-100 rounded-md px-4 py-2.5 bg-slate-50">
                <span className="text-slate-500 font-medium">Est. travel time</span>
                <span className="font-bold text-slate-800">{formatDuration(routeData?.duration)}</span>
              </div>
              <div className="flex items-center justify-between text-sm border border-slate-100 rounded-md px-4 py-2.5 bg-slate-50">
                <span className="text-slate-500 font-medium">Route mode</span>
                <span className="font-bold text-slate-800">Road / Rail</span>
              </div>
              <div className="flex items-center justify-between text-sm border border-slate-100 rounded-md px-4 py-2.5 bg-slate-50">
                <span className="text-slate-500 font-medium">Origin</span>
                <span className="font-bold text-slate-800 truncate ml-4">{fromAP.name || fromAP.city}</span>
              </div>
              <div className="flex items-center justify-between text-sm border border-slate-100 rounded-md px-4 py-2.5 bg-slate-50">
                <span className="text-slate-500 font-medium">Destination</span>
                <span className="font-bold text-slate-800 truncate ml-4">{toAP.name || toAP.city}</span>
              </div>
            </CardContent>
          </Card>


          <div className="mt-6 flex flex-wrap items-center gap-2">
            <Button size="sm" className="gap-1.5 bg-slate-900 text-white hover:bg-slate-800">
              <Clock3 className="size-4" />
              View timeline
            </Button>
            <Button variant="outline" size="sm" className="gap-1.5 border-slate-200 text-slate-700 hover:bg-slate-50">
              <UserRound className="size-4" />
              Contact carrier
            </Button>
          </div>
        </div>

        <div className="relative h-[400px] overflow-hidden bg-slate-100 md:h-full md:border-l border-slate-200">
          <Map
            ref={mapRef}
            loading={loading}
            center={[(fromAP.lon + toAP.lon) / 2, (fromAP.lat + toAP.lat) / 2]}
            zoom={zoom}
            pitch={60}
            styles={{
              light: "https://tiles.openfreemap.org/styles/liberty",
              dark: "https://tiles.openfreemap.org/styles/liberty",
            }}
          >
            <MapControls position="top-right" showZoom showCompass showFullscreen/>
            <MapRoute
              id="delivery-full-route"
              coordinates={routeData?.coordinates ?? []}
              color="#3b82f6"
              width={6}
              opacity={0.95}
              interactive={false}
            />

            <MapMarker longitude={fromAP.lon} latitude={fromAP.lat}>
              <MarkerContent>
                <div className="size-4 rounded-full border-2 border-white bg-emerald-500 shadow-sm" />
              </MarkerContent>
              <MarkerTooltip><span className="text-xs text-slate-800 text-nowrap">Supplier: {fromAP.name}</span></MarkerTooltip>
            </MapMarker>

            <MapMarker longitude={toAP.lon} latitude={toAP.lat}>
              <MarkerContent>
                <div className="size-4 rounded-full border-2 border-white bg-rose-500 shadow-sm" />
              </MarkerContent>
              <MarkerTooltip><span className="text-xs text-slate-800 text-nowrap">Logistics Hub: {toAP.name}</span></MarkerTooltip>
            </MapMarker>
          </Map>
        </div>
      </div>
    </div>
  );
}

function AirRouteViewer({ fromAP, toAP, incTitle, costUsd, mode, hubs }: { fromAP: AP, toAP: AP, incTitle: string, costUsd: number, mode: "air"|"sea", hubs: AP[] }) {
  const navigate = useNavigate();
  const mapRef = useRef<MapRef>(null);
  const [active, setActive] = useState(0);

  const routes = useMemo(()=>computeRoutes(fromAP,toAP,hubs).slice(0, 2),[fromAP,toAP,hubs]);
  const sel = routes[active] || routes[0];

  const center: [number,number] = [(fromAP.lon+toAP.lon)/2,(fromAP.lat+toAP.lat)/2];
  const distKm = routes[0]?.distKm || 0;
  const zoom   = distKm>8000?2:distKm>4000?2.8:distKm>2000?3.8:distKm>500?5:7;

  // Guard: same location
  if (distKm < 1) {
    return (
      <div style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",height:"calc(100vh - 120px)",background:"#f8fafc",gap:16}}>
        <button onClick={()=>navigate(-1)} style={{position:"absolute",top:24,left:24,display:"flex",alignItems:"center",gap:6,fontSize:11,fontFamily:"monospace",fontWeight:700,textTransform:"uppercase",color:"#64748b",background:"#fff",border:"1px solid #e2e8f0",borderRadius:6,padding:"5px 10px",cursor:"pointer"}}>
          <ArrowLeft size={13}/> Back
        </button>
        <div style={{background:"#fff",border:"1px solid #fecaca",borderRadius:12,padding:"28px 36px",textAlign:"center",maxWidth:420}}>
          <p style={{fontSize:12,fontFamily:"monospace",fontWeight:700,textTransform:"uppercase",letterSpacing:".1em",color:"#94a3b8",marginBottom:12}}>Route Unavailable</p>
          <p style={{fontSize:15,fontWeight:700,color:"#0f172a",margin:"0 0 8px"}}>Origin and destination are the same location</p>
          <p style={{fontSize:13,color:"#64748b",margin:0}}>{fromAP.name || fromAP.city} — no route can be plotted when both points are identical. Check that the supplier nodes have distinct coordinates in the backend.</p>
        </div>
      </div>
    );
  }

  const MAP_2D = "https://tiles.openfreemap.org/styles/bright";

  const accentBg    = mode==="air"?"#fef2f2":"#eff6ff";
  const accentBdr   = mode==="air"?"#fecaca":"#bfdbfe";
  const accentText  = mode==="air"?"#dc2626":"#2563eb";

  return (
    <div style={{display:"flex",flexDirection:"column",height:"calc(100vh - 120px)",background:"#f8fafc",fontFamily:"Inter,system-ui,sans-serif"}}>
      {/* Header */}
      <div style={{flexShrink:0,background:"#fff",borderBottom:"1px solid #e2e8f0",padding:"10px 18px",display:"flex",alignItems:"center",gap:12,boxShadow:"0 1px 2px rgba(0,0,0,.05)"}}>
        <button onClick={()=>navigate(-1)} style={{display:"flex",alignItems:"center",gap:6,fontSize:11,fontFamily:"monospace",fontWeight:700,textTransform:"uppercase",letterSpacing:".08em",color:"#64748b",background:"#f8fafc",border:"1px solid #e2e8f0",borderRadius:6,padding:"5px 10px",cursor:"pointer"}}>
          <ArrowLeft size={13}/> Back
        </button>
        <div style={{display:"flex",alignItems:"center",gap:10,flex:1,minWidth:0}}>
          {mode==="air"?<Plane size={15} style={{color:"#dc2626",flexShrink:0}}/>:<Plane size={15} style={{color:"#2563eb",flexShrink:0}}/>}
          <div>
            <p style={{fontSize:10,fontFamily:"monospace",fontWeight:700,textTransform:"uppercase",letterSpacing:".1em",color:"#94a3b8",margin:0}}>
              {mode==="air"?"Air Freight":"Sea Freight"} · {incTitle}
            </p>
            <p style={{fontSize:13,fontWeight:700,color:"#0f172a",margin:0}}>
              {fromAP.city} ({fromAP.iata||fromAP.icao}) → {toAP.city} ({toAP.iata||toAP.icao})
            </p>
          </div>
        </div>
        <div style={{display:"flex",gap:8,flexShrink:0}}>
          {[
            {icon:<MapPin size={11}/>,  v:`${Math.round(distKm).toLocaleString()} km`, c:"#475569", bg:"#f8fafc", b:"#e2e8f0"},
            {icon:<Clock size={11}/>,   v:`${routes[0]?Math.round(routes[0].hours)+"h":"—"}`, c:"#475569", bg:"#f8fafc", b:"#e2e8f0"},
            ...(costUsd>0?[{icon:<DollarSign size={11}/>,v:`$${costUsd.toLocaleString()}`,c:"#dc2626",bg:"#fef2f2",b:"#fecaca"}]:[]),
          ].map((p,i)=>(
            <span key={i} style={{display:"flex",alignItems:"center",gap:5,fontSize:11,fontFamily:"monospace",fontWeight:700,color:p.c,border:`1px solid ${p.b}`,background:p.bg,borderRadius:6,padding:"4px 9px"}}>{p.icon}{p.v}</span>
          ))}
        </div>
      </div>

      {/* Body */}
      <div style={{display:"flex",flex:1,minHeight:0}}>
        {/* Map */}
        <div style={{flex:1,position:"relative",overflow:"hidden"}}>
          <Map ref={mapRef} theme="light" styles={{light:MAP_2D,dark:MAP_2D}}
            center={center} zoom={zoom} pitch={0} bearing={0} className="w-full h-full">
            <MapControls position="bottom-right" showZoom showCompass showFullscreen/>

            {/* All routes — dim inactive */}
            {routes.map((r,i)=>{
              const isActive = i===active;
              return r.legs.slice(0,-1).map((leg,j)=>{
                const coords = arc(leg, r.legs[j+1]);
                return [
                  <MapRoute key={`g-${i}-${j}`} id={`glow-${i}-${j}`} coordinates={coords}
                    color={r.color} width={isActive?14:0} opacity={0.15} interactive={false}/>,
                  <MapRoute key={`r-${i}-${j}`} id={`rt-${i}-${j}`} coordinates={coords}
                    color={r.color} width={isActive?3.5:1.5} opacity={isActive?0.95:0.35}
                    dashArray={r.dash} interactive={false}/>,
                ];
              });
            })}
          </Map>

          {/* Map legend */}
          <div style={{position:"absolute",bottom:52,left:12,zIndex:10,background:"rgba(255,255,255,.92)",backdropFilter:"blur(8px)",border:"1px solid #e2e8f0",borderRadius:10,padding:"12px 14px",boxShadow:"0 2px 8px rgba(0,0,0,.08)"}}>
            <p style={{fontSize:9,fontFamily:"monospace",fontWeight:700,textTransform:"uppercase",letterSpacing:".1em",color:"#94a3b8",margin:"0 0 8px"}}>Routes</p>
            {routes.map((r,i)=>(
              <div key={i} onClick={()=>setActive(i)} style={{display:"flex",alignItems:"center",gap:8,marginBottom:5,cursor:"pointer",opacity:i===active?1:.55}}>
                <span style={{display:"inline-block",width:24,height:3,borderRadius:2,background:r.color}}/>
                <span style={{fontSize:11,fontFamily:"monospace",fontWeight:i===active?700:400,color:"#334155"}}>{r.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Side panel */}
        <div style={{width:296,flexShrink:0,background:"#fff",borderLeft:"1px solid #e2e8f0",overflowY:"auto",display:"flex",flexDirection:"column"}}>
          <div style={{padding:"12px 18px",borderBottom:"1px solid #e2e8f0",background:"#f8fafc"}}>
            <p style={{fontSize:9,fontFamily:"monospace",fontWeight:700,textTransform:"uppercase",letterSpacing:".1em",color:"#94a3b8",margin:0}}>Route Options · {routes.length}</p>
          </div>

          <div style={{padding:16,display:"flex",flexDirection:"column",gap:10}}>
            {routes.map((r,i)=>{
              const isA = i===active;
              return (
                <div key={i} onClick={()=>setActive(i)} style={{border:`1.5px solid ${isA?r.color:"#e2e8f0"}`,borderRadius:10,padding:"12px 14px",background:isA?"#fafcff":"#fff",cursor:"pointer",boxShadow:isA?"0 2px 12px rgba(0,0,0,.07)":"none",transition:"all .15s"}}>
                  <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:6}}>
                    <div style={{display:"flex",alignItems:"center",gap:7}}>
                      <span style={{width:10,height:10,borderRadius:"50%",background:r.color,flexShrink:0}}/>
                      <span style={{fontSize:12,fontWeight:700,color:"#0f172a"}}>{r.label}</span>
                      {i===0&&<span style={{fontSize:9,fontFamily:"monospace",fontWeight:700,textTransform:"uppercase",color:accentText,background:accentBg,border:`1px solid ${accentBdr}`,borderRadius:4,padding:"1px 6px"}}>Best</span>}
                    </div>
                    {isA&&<span style={{fontSize:9,fontFamily:"monospace",color:"#16a34a",fontWeight:700}}>● Active</span>}
                  </div>
                  <div style={{display:"flex",gap:14,fontSize:11,fontFamily:"monospace",color:"#64748b"}}>
                    <span style={{display:"flex",alignItems:"center",gap:4}}><MapPin size={10}/>{Math.round(r.distKm).toLocaleString()} km</span>
                    <span style={{display:"flex",alignItems:"center",gap:4}}><Clock size={10}/>
                      {r.hours<24?`${Math.round(r.hours)}h`:`${Math.floor(r.hours/24)}d ${Math.round(r.hours%24)}h`}
                    </span>
                  </div>
                  {r.legs.length>2&&(
                    <div style={{marginTop:6,fontSize:10,fontFamily:"monospace",color:"#94a3b8"}}>
                      Stop: {r.legs.slice(1,-1).map(h=>h.city).join(" → ")}
                    </div>
                  )}
                </div>
              );
            })}

            <div style={{borderTop:"1px solid #e2e8f0",paddingTop:14,marginTop:4}}>
              <p style={{fontSize:9,fontFamily:"monospace",fontWeight:700,textTransform:"uppercase",letterSpacing:".1em",color:"#94a3b8",marginBottom:10}}>Selected Route Detail</p>
              <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:8,marginBottom:12}}>
                {[
                  {l:"Distance",v:`${Math.round(sel?.distKm||0).toLocaleString()} km`,icon:<MapPin size={10}/>,c:"#0f172a"},
                  {l:"Travel Time",v:sel?.hours?sel.hours<24?`${Math.round(sel.hours)}h`:`${Math.floor(sel.hours/24)}d ${Math.round(sel.hours%24)}h`:"—",icon:<Clock size={10}/>,c:"#0f172a"},
                  {l:"Speed",v:"900 km/h",icon:<Navigation size={10}/>,c:accentText},
                  {l:"Stops",v:`${(sel?.legs?.length||2)-2}`,icon:<Plane size={10}/>,c:"#64748b"},
                ].map(m=>(
                  <div key={m.l} style={{border:"1px solid #e2e8f0",borderRadius:8,padding:"10px 12px",background:"#fff"}}>
                    <div style={{display:"flex",alignItems:"center",gap:4,marginBottom:5,color:"#94a3b8"}}>{m.icon}<span style={{fontSize:9,fontFamily:"monospace",fontWeight:700,textTransform:"uppercase",letterSpacing:".08em"}}>{m.l}</span></div>
                    <div style={{fontSize:15,fontWeight:700,color:m.c}}>{m.v}</div>
                  </div>
                ))}
              </div>
              {([{label:"Supplier",ap:fromAP,dot:"#16a34a"},{label:"Logistics Hub",ap:toAP,dot:"#dc2626"}]).map(({label,ap,dot})=>(
                <div key={label} style={{border:"1px solid #e2e8f0",borderRadius:8,padding:"10px 12px",background:"#fff",marginBottom:8}}>
                  <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:4}}>
                    <span style={{width:7,height:7,borderRadius:"50%",background:dot,flexShrink:0}}/>
                    <span style={{fontSize:9,fontFamily:"monospace",fontWeight:700,textTransform:"uppercase",letterSpacing:".1em",color:"#94a3b8"}}>{label}</span>
                  </div>
                  <p style={{fontSize:12,fontWeight:700,color:"#0f172a",margin:0}}>{ap.name || ap.city}</p>
                  <p style={{fontSize:10,fontFamily:"monospace",color:"#64748b",margin:"2px 0 6px"}}>{ap.city !== ap.name ? ap.city : ""}{ap.country ? " · " + ap.country : ""}</p>
                  <div style={{display:"flex",gap:5}}>
                    {ap.iata && <span style={{fontSize:9,fontFamily:"monospace",fontWeight:700,color:"#2563eb",background:"#eff6ff",border:"1px solid #bfdbfe",borderRadius:3,padding:"1px 5px"}}>IATA {ap.iata}</span>}
                    {ap.icao && <span style={{fontSize:9,fontFamily:"monospace",color:"#94a3b8",background:"#f8fafc",border:"1px solid #e2e8f0",borderRadius:3,padding:"1px 5px"}}>ICAO {ap.icao}</span>}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}


/* ── Main Entry ─────────────────────────────────────────────────────── */
export default function RouteViewer() {
  const [params] = useSearchParams();

  const mode     = (params.get("mode") || "air") as "air"|"land"|"sea";
  const costUsd  = Number(params.get("cost") || 0);
  const incTitle = params.get("incident") || "Route Visualisation";

  // ── Prefer real lat/lng coords if passed (new dynamic path) ──────────
  const fromLat = parseFloat(params.get("fromLat") || "");
  const fromLng = parseFloat(params.get("fromLng") || "");
  const fromLabel = params.get("fromLabel") || "";
  const toLat   = parseFloat(params.get("toLat") || "");
  const toLng   = parseFloat(params.get("toLng") || "");
  const toLabel = params.get("toLabel") || "";

  const hasRealCoords = !isNaN(fromLat) && !isNaN(fromLng) && !isNaN(toLat) && !isNaN(toLng)
                        && (fromLat !== 0 || fromLng !== 0 || toLat !== 0 || toLng !== 0);

  // ── Legacy IATA code path (used when lat/lng not provided) ────────────
  const fromCode = (params.get("from") || "HKG").toUpperCase();
  const toCode   = (params.get("to")   || "LHR").toUpperCase();

  const [airports, setAirports] = useState<Record<string,AP>>({});

  useEffect(()=>{ fetch("/airports.json").then(r=>r.json()).then(setAirports).catch(()=>{}); },[]);

  const iataIdx = useMemo<Record<string,AP>>(()=>{
    const idx: Record<string,AP>={};
    for (const ap of Object.values(airports)) if(ap.iata?.trim()) idx[ap.iata.trim().toUpperCase()]=ap;
    return idx;
  },[airports]);

  // Build AP objects — real coords take priority
  const fromAP: AP = hasRealCoords
    ? { icao: "", iata: "", name: fromLabel, city: fromLabel, country: "", lat: fromLat, lon: fromLng }
    : (iataIdx[fromCode] || STUB[fromCode] || STUB.HKG);

  const toAP: AP = hasRealCoords
    ? { icao: "", iata: "", name: toLabel, city: toLabel, country: "", lat: toLat, lon: toLng }
    : (iataIdx[toCode] || STUB[toCode] || STUB.LHR);

  const hubs = useMemo(()=>HUB_IATA.map(c=>iataIdx[c]||STUB[c]).filter(Boolean),[iataIdx]);

  // Don't render until airports.json is loaded (or we have real coords so we don't need it)
  if (!hasRealCoords && Object.keys(airports).length === 0) return null;

  if (mode === "land") {
    return <LandRouteViewer fromAP={fromAP} toAP={toAP} incTitle={incTitle} />;
  }

  return <AirRouteViewer fromAP={fromAP} toAP={toAP} incTitle={incTitle} costUsd={costUsd} mode={mode} hubs={hubs} />;
}
