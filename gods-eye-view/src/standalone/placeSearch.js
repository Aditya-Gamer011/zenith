import {
  createPlaceSearch,
  createGoogleGeocoder,
  createPhotonGeocoder,
} from '../search/index.js';
import { CITY_POIS, findPoiByName, parseQueryCoordinates } from '../locations.js';

/** Instant resolver for raw coordinates and curated presets/POIs. */
function createCoordinateAndPresetGeocoder() {
  return {
    async geocode(query, { signal } = {}) {
      signal?.throwIfAborted();
      const text = String(query ?? '').trim();
      if (!text) return { place: null, answered: true };

      // 1. Direct coordinate lookup (e.g. "48.8584, 2.2945" or "37.7749, -122.4194")
      const coords = parseQueryCoordinates(text);
      if (coords) {
        return {
          place: {
            lat: coords.lat,
            lng: coords.lng,
            name: coords.label,
            label: coords.label,
            types: [],
            viewport: null,
          },
          answered: true,
        };
      }

      // 2. Curated preset POI lookup (e.g. "Eiffel Tower", "Tokyo Tower", "Texas State Capitol")
      const poiMatch = findPoiByName(text);
      if (poiMatch) {
        const city = CITY_POIS[poiMatch.cityId];
        const poi = city?.pois?.[poiMatch.index];
        if (poi) {
          return {
            place: {
              lat: poi.lat,
              lng: poi.lon,
              name: poi.name,
              label: `${poi.name}, ${city.name}`,
              types: [],
              viewport: null,
            },
            answered: true,
          };
        }
      }

      // 3. Preset city lookup (e.g. "Austin", "Tokyo", "Paris", "London")
      const lower = text.toLowerCase();
      for (const [cId, city] of Object.entries(CITY_POIS)) {
        if (city.name.toLowerCase() === lower || cId === lower) {
          const firstPoi = city.pois?.[0];
          return {
            place: {
              lat: firstPoi?.lat,
              lng: firstPoi?.lon,
              name: city.name,
              label: city.name,
              types: ['locality'],
              viewport: city.viewBounds || null,
            },
            answered: true,
          };
        }
      }

      return { place: null, answered: false };
    },
  };
}

/** Zenith unified backend geocoder adapter. */
function createZenithGeocoder({ fetchImpl = fetch } = {}) {
  return {
    async geocode(query, { bias, signal } = {}) {
      signal?.throwIfAborted();
      const text = String(query ?? '').trim();
      if (!text) return { place: null, answered: true };
      try {
        const origin = (typeof window !== 'undefined' && window.location?.origin)
          ? window.location.origin
          : 'http://localhost:8005';
        const url = new URL('/api/gev/geocode', origin);
        url.searchParams.set('q', text);
        if (bias) url.searchParams.set('bias', bias);
        const res = await fetchImpl(url.toString(), { signal });
        if (!res.ok) return { place: null, answered: false };
        const data = await res.json();
        signal?.throwIfAborted();
        if (data && data.ok && data.found && data.place) {
          return { place: data.place, answered: true };
        }
        return { place: null, answered: Boolean(data?.ok) };
      } catch {
        signal?.throwIfAborted();
        return { place: null, answered: false };
      }
    },
  };
}

/** Coordinates/Presets first, then Zenith backend, then Google direct, then keyless Photon. */
export function createStandalonePlaceSearch({
  resolveApiKey,
  fetchImpl = (...args) => fetch(...args),
  signal,
} = {}) {
  return createPlaceSearch({
    signal,
    providers: [
      createCoordinateAndPresetGeocoder(),
      createZenithGeocoder({ fetchImpl }),
      createGoogleGeocoder({
        request(query, { bias, signal }) {
          const key = resolveApiKey?.();
          if (!key) return null;
          const url = new URL(
            'https://maps.googleapis.com/maps/api/geocode/json',
          );
          url.searchParams.set('address', query);
          url.searchParams.set('key', key);
          if (bias) url.searchParams.set('bounds', bias);
          return fetchImpl(url.toString(), { signal });
        },
      }),
      createPhotonGeocoder({ fetchImpl }),
    ],
  });
}
