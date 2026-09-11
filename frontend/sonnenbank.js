/**
 * Sonnenstand an einer Bank - Laufzeitteil.
 *
 * Der Sonnenstand ist bewusst als Portierung desselben NOAA-Verfahrens
 * umgesetzt, das die Python-Pipeline verwendet. So liefern Vorberechnung
 * und App garantiert identische Werte.
 *
 *   import { istSonnig, tagesverlauf } from './sonnenbank.js';
 *
 *   const profil = bank.horizont;   // 360 Werte in Zehntelgrad
 *   const jetzt  = istSonnig(profil, bank.lat, bank.lon, new Date());
 */

const RAD = Math.PI / 180;

/** Sonnenstand fuer einen Zeitpunkt. Azimut 0 = Nord, im Uhrzeigersinn. */
export function sonnenstand(datum, lat, lon) {
  const n = datum.getTime() / 86400000 + 2440587.5 - 2451545.0;

  const L = (280.460 + 0.9856474 * n) * RAD;
  const g = (357.528 + 0.9856003 * n) * RAD;
  const lam = L + 1.915 * RAD * Math.sin(g) + 0.020 * RAD * Math.sin(2 * g);
  const eps = (23.439 - 0.0000004 * n) * RAD;

  const ra = Math.atan2(Math.cos(eps) * Math.sin(lam), Math.cos(lam));
  const dec = Math.asin(Math.sin(eps) * Math.sin(lam));

  const gmst = (18.697374558 + 24.06570982441908 * n) % 24;
  const lmst = (((gmst + lon / 15) % 24) + 24) % 24 * 15 * RAD;
  const ha = lmst - ra;

  const phi = lat * RAD;
  const hoehe = Math.asin(
    Math.sin(phi) * Math.sin(dec) + Math.cos(phi) * Math.cos(dec) * Math.cos(ha),
  );
  const azimut = Math.atan2(
    -Math.sin(ha),
    Math.tan(dec) * Math.cos(phi) - Math.sin(phi) * Math.cos(ha),
  );

  return {
    azimut: ((azimut / RAD) % 360 + 360) % 360,
    hoehe: hoehe / RAD,
  };
}

/** Atmosphaerische Refraktion in Grad (Naeherung nach Saemundsson). */
export function refraktion(hoehe) {
  if (hoehe < -1) return 0;
  return 1.02 / Math.tan((hoehe + 10.3 / (hoehe + 5.11)) * RAD) / 60;
}

/** Horizonthoehe des Profils fuer ein beliebiges Azimut, linear interpoliert. */
export function horizontBei(profil, azimut) {
  const a = ((azimut % 360) + 360) % 360;
  const i = Math.floor(a);
  const f = a - i;
  const h0 = profil[i % 360] / 10;
  const h1 = profil[(i + 1) % 360] / 10;
  return h0 + (h1 - h0) * f;
}

/**
 * Zustand an der Bank zu einem Zeitpunkt.
 * @returns {{sonnig: boolean, hoehe: number, azimut: number,
 *            horizont: number, ueberHorizont: number, grund: string}}
 */
export function istSonnig(profil, lat, lon, datum = new Date()) {
  const { azimut, hoehe } = sonnenstand(datum, lat, lon);
  const sichtbar = hoehe + refraktion(hoehe);
  const horizont = horizontBei(profil, azimut);

  let grund = 'Sonne';
  if (sichtbar <= 0) grund = 'Sonne untergegangen';
  else if (sichtbar <= horizont) grund = 'von Bebauung oder Gelände verdeckt';

  return {
    sonnig: sichtbar > 0 && sichtbar > horizont,
    hoehe: sichtbar,
    azimut,
    horizont,
    ueberHorizont: sichtbar - horizont,
    grund,
  };
}

/**
 * Sonnen- und Schattenphasen eines Tages.
 * @param {number} schrittMinuten Aufloesung der Suche
 * @returns {Array<{von: Date, bis: Date, sonnig: boolean}>}
 */
export function tagesverlauf(profil, lat, lon, tag = new Date(), schrittMinuten = 2) {
  const start = new Date(tag);
  start.setHours(0, 0, 0, 0);
  const ende = new Date(start.getTime() + 86400000);

  const phasen = [];
  let aktuell = null;
  let von = new Date(start);

  for (let t = new Date(start); t < ende; t = new Date(t.getTime() + schrittMinuten * 60000)) {
    const zustand = istSonnig(profil, lat, lon, t).sonnig;
    if (aktuell === null) {
      aktuell = zustand;
    } else if (zustand !== aktuell) {
      phasen.push({ von, bis: new Date(t), sonnig: aktuell });
      von = new Date(t);
      aktuell = zustand;
    }
  }
  phasen.push({ von, bis: ende, sonnig: aktuell });
  return phasen;
}

/** Naechster Wechsel Sonne/Schatten ab jetzt, oder null bis Tagesende. */
export function naechsterWechsel(profil, lat, lon, ab = new Date(), schrittMinuten = 2) {
  const jetzt = istSonnig(profil, lat, lon, ab).sonnig;
  const grenze = new Date(ab.getTime() + 86400000);

  for (let t = new Date(ab); t < grenze; t = new Date(t.getTime() + schrittMinuten * 60000)) {
    if (istSonnig(profil, lat, lon, t).sonnig !== jetzt) {
      // Auf die Minute genau nachfassen
      for (let u = new Date(t.getTime() - schrittMinuten * 60000); u <= t; u = new Date(u.getTime() + 60000)) {
        if (istSonnig(profil, lat, lon, u).sonnig !== jetzt) {
          return { zeitpunkt: u, wirdSonnig: !jetzt };
        }
      }
      return { zeitpunkt: t, wirdSonnig: !jetzt };
    }
  }
  return null;
}

/** Sonnenstunden eines Tages in Stunden. */
export function sonnenstunden(profil, lat, lon, tag = new Date()) {
  return tagesverlauf(profil, lat, lon, tag, 2)
    .filter((p) => p.sonnig)
    .reduce((summe, p) => summe + (p.bis - p.von) / 3600000, 0);
}

/**
 * Dekodiert ein Profil aus der kompakten Base64-Form (Schritt 6).
 * 360 Bytes, ein Byte je Grad Azimut, Wert in halben Grad.
 * @returns {number[]} 360 Werte in Zehntelgrad – dasselbe Format wie
 *          horizons.json, damit alle Funktionen hier unverändert passen.
 */
export function dekodiereHorizont(base64) {
  const roh = atob(base64);
  const profil = new Array(360);
  for (let i = 0; i < 360; i++) profil[i] = roh.charCodeAt(i) * 5;
  return profil;
}
