import { useState } from 'react'

/**
 * Pour utiliser le VRAI logo Tanger Med Port Authority :
 * 1. Place ton fichier logo (PNG/SVG que tu as le droit d'utiliser pour ton PFA)
 *    dans `frontend/public/logo.png`
 * 2. C'est tout — ce composant l'affichera automatiquement à la place de
 *    l'emblème générique ci-dessous (voir le <img onError=... /> plus bas).
 */
export default function Logo({ size = 34 }) {
  const [imgFailed, setImgFailed] = useState(false)

  if (!imgFailed) {
    return (
      <img
        src="/logo.png"
        alt="Tanger Med Port Authority"
        
        height={size}
        style={{ display: 'block', objectFit: 'contain' }}
        onError={() => setImgFailed(true)}
      />
    )
  }


}
