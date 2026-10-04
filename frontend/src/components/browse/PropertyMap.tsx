"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { useEffect, useMemo } from "react";
import { MapContainer, Marker, TileLayer, Tooltip, useMap } from "react-leaflet";

export interface MapPoint {
  id: number;
  name: string;
  lat: number;
  lon: number;
  label: string;
}

interface PropertyMapProps {
  points: MapPoint[];
  office: { label: string; lat: number; lon: number } | null;
  activeId: number | null;
  onSelect: (id: number) => void;
}

const BAY_AREA_CENTER: L.LatLngTuple = [37.42, -122.05];

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (char) => `&#${char.charCodeAt(0)};`);
}

function pinIcon(label: string, active: boolean): L.DivIcon {
  return L.divIcon({
    className: "price-pin-anchor",
    iconSize: [0, 0],
    html: `<span class="price-pin${active ? " price-pin--active" : ""}">${escapeHtml(label)}</span>`,
  });
}

const officeIcon = L.divIcon({ className: "price-pin-anchor", iconSize: [0, 0], html: '<span class="office-pin">Office</span>' });

function FitToPoints({ points, office }: Pick<PropertyMapProps, "points" | "office">) {
  const map = useMap();

  useEffect(() => {
    const coordinates: L.LatLngTuple[] = points.map((p) => [p.lat, p.lon]);
    if (office) coordinates.push([office.lat, office.lon]);
    if (coordinates.length === 0) return;
    map.fitBounds(L.latLngBounds(coordinates), { padding: [48, 48], maxZoom: 14 });
  }, [map, points, office]);

  return null;
}

export default function PropertyMap({ points, office, activeId, onSelect }: PropertyMapProps) {
  const icons = useMemo(
    () => new Map(points.map((p) => [p.id, { idle: pinIcon(p.label, false), active: pinIcon(p.label, true) }])),
    [points],
  );

  return (
    <MapContainer center={BAY_AREA_CENTER} zoom={11} scrollWheelZoom className="h-full w-full">
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors'
        maxZoom={19}
      />
      <FitToPoints points={points} office={office} />
      {office && (
        <Marker position={[office.lat, office.lon]} icon={officeIcon} title={office.label} keyboard={false}>
          <Tooltip direction="top" offset={[0, -24]}>
            {office.label}
          </Tooltip>
        </Marker>
      )}
      {points.map((point) => {
        const active = point.id === activeId;
        const icon = icons.get(point.id);
        return (
          <Marker
            key={point.id}
            position={[point.lat, point.lon]}
            icon={active ? icon?.active : icon?.idle}
            title={`${point.name} — ${point.label}`}
            zIndexOffset={active ? 1000 : 0}
            eventHandlers={{ click: () => onSelect(point.id) }}
          >
            <Tooltip direction="top" offset={[0, -26]}>
              {point.name}
            </Tooltip>
          </Marker>
        );
      })}
    </MapContainer>
  );
}
