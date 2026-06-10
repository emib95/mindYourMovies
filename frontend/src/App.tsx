import './App.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, MouseEvent } from 'react'
import mindTheMovieLogo from './assets/mind-the-movie.svg'

type ProviderId = 'netflix' | 'disney' | 'prime' | 'youtube' | 'hbo'
type Language = 'en' | 'es'
type LocationStatus = 'detecting' | 'detected' | 'default' | 'error' | 'manual'

type Recommendation = {
  movie_title: string
  provider: string
  watch_link: string
  reason: string
  why_recommended: string
  region: string
  language: Language
}

type LocationResponse = {
  region: string
  source: 'header' | 'ip' | 'default'
  detected: boolean
}

const providers: Array<{ id: ProviderId; label: string }> = [
  { id: 'netflix', label: 'Netflix' },
  { id: 'disney', label: 'Disney+' },
  { id: 'prime', label: 'Prime Video' },
  { id: 'youtube', label: 'YouTube' },
  { id: 'hbo', label: 'HBO / NOW' },
]

const languageOptions: Array<{ id: Language; flag: string; path: string }> = [
  { id: 'en', flag: '🇬🇧', path: '/' },
  { id: 'es', flag: '🇪🇸', path: '/es' },
]

const regionOptions = [
  'GB',
  'US',
  'ES',
  'MX',
  'AR',
  'CO',
  'CL',
  'PE',
  'CA',
  'AU',
  'IE',
  'FR',
  'DE',
  'IT',
  'NL',
  'BR',
]

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
).replace(/\/+$/, '')
const donationUrl = (
  import.meta.env.VITE_DONATION_URL ??
  'https://buy.stripe.com/28E5kD9Am5ku4DIavWfYY00'
).trim()
const creatorPhotoUrl = (
  import.meta.env.VITE_CREATOR_PHOTO_URL ?? '/emilio-banqueri.jpg'
).trim()

const translations = {
  en: {
    appAlt: 'Mind the Movie',
    languageSwitcherLabel: 'Choose language',
    title: 'Stop scrolling. Pick one movie.',
    intro:
      'Tell us which providers you can use and what everyone feels like watching. We will suggest one movie with a simple way to start it.',
    languageLabel: 'Language',
    locationLabel: 'Detected location',
    changeLocationLabel: 'Change availability country',
    regionLabel: 'Availability country',
    regionHelp: {
      detecting: 'Detecting your country from your IP address...',
      detected: (country: string) =>
        `Detected location is ${country}. You can change it here.`,
      default: (country: string) =>
        `Using ${country} as a fallback. You can change it here.`,
      error: (country: string) =>
        `Could not detect your country, so ${country} is selected for now. You can change it here.`,
      manual: (country: string) =>
        `Using availability for ${country}. You can change it here.`,
    },
    languages: {
      en: 'English',
      es: 'Spanish',
    },
    countries: {
      GB: 'United Kingdom',
      US: 'United States',
      ES: 'Spain',
      MX: 'Mexico',
      AR: 'Argentina',
      CO: 'Colombia',
      CL: 'Chile',
      PE: 'Peru',
      CA: 'Canada',
      AU: 'Australia',
      IE: 'Ireland',
      FR: 'France',
      DE: 'Germany',
      IT: 'Italy',
      NL: 'Netherlands',
      BR: 'Brazil',
    },
    providerLegend: 'Which providers can you use?',
    paidOption: 'I am willing to pay extra for rentals or purchases.',
    paidOptionHelp:
      'When unchecked, results exclude paid rent/buy options such as many YouTube movies.',
    moodLabel: 'What do you feel like watching?',
    moodPlaceholder:
      'Funny, tense thriller, comfort movie, visually stunning...',
    groupLabel: 'Who is watching?',
    groupPlaceholder: 'Date night, family, friends who cannot agree...',
    notesLabel: 'Optional comment',
    notesPlaceholder: 'Avoid horror, under two hours, no subtitles tonight...',
    loading: 'Choosing...',
    submit: 'Recommend one movie',
    pick: "Tonight's pick",
    whyRecommended: 'Why this recommendation?',
    watchOn: (provider: string) => `Watch on ${provider}`,
    donationEyebrow: 'Support',
    donationTitle: 'Buy me a coffee',
    donationCopy:
      'If Mind the Movie saved your evening, you can support the project with a small donation.',
    donationCta: 'Donate with Stripe',
    donationUnavailable:
      'Donations will be available once a Stripe payment link is configured.',
    creatorName: 'Emilio Banqueri',
    creatorBio:
      'I am Emilio Banqueri, a developer who wants technology to actually support our wellbeing. I built this because mindless scrolling and too many choices can quietly weigh on our mental health.',
    creatorPhotoAlt: 'Emilio Banqueri',
    errors: {
      recommendation: 'Could not get a recommendation.',
      generic: 'Something went wrong while choosing a movie.',
    },
  },
  es: {
    appAlt: 'Mind the Movie',
    languageSwitcherLabel: 'Elegir idioma',
    title: 'Deja de buscar. Elige una pelicula.',
    intro:
      'Dinos que plataformas puedes usar y que les apetece ver. Te sugeriremos una pelicula con una forma sencilla de empezar.',
    languageLabel: 'Idioma',
    locationLabel: 'Ubicacion detectada',
    changeLocationLabel: 'Cambiar pais de disponibilidad',
    regionLabel: 'Pais de disponibilidad',
    regionHelp: {
      detecting: 'Detectando tu pais por tu direccion IP...',
      detected: (country: string) =>
        `Ubicacion detectada: ${country}. Puedes cambiarla aqui.`,
      default: (country: string) =>
        `Usando ${country} como opcion inicial. Puedes cambiarla aqui.`,
      error: (country: string) =>
        `No pudimos detectar tu pais, asi que ${country} esta seleccionado por ahora. Puedes cambiarlo aqui.`,
      manual: (country: string) =>
        `Usando la disponibilidad de ${country}. Puedes cambiarla aqui.`,
    },
    languages: {
      en: 'Ingles',
      es: 'Espanol',
    },
    countries: {
      GB: 'Reino Unido',
      US: 'Estados Unidos',
      ES: 'Espana',
      MX: 'Mexico',
      AR: 'Argentina',
      CO: 'Colombia',
      CL: 'Chile',
      PE: 'Peru',
      CA: 'Canada',
      AU: 'Australia',
      IE: 'Irlanda',
      FR: 'Francia',
      DE: 'Alemania',
      IT: 'Italia',
      NL: 'Paises Bajos',
      BR: 'Brasil',
    },
    providerLegend: 'Que plataformas puedes usar?',
    paidOption: 'Estoy dispuesto a pagar extra por alquileres o compras.',
    paidOptionHelp:
      'Si no esta marcada, los resultados excluyen opciones de alquiler/compra como muchas peliculas de YouTube.',
    moodLabel: 'Que te apetece ver?',
    moodPlaceholder:
      'Comedia, thriller tenso, pelicula reconfortante, algo visual...',
    groupLabel: 'Quien va a ver la pelicula?',
    groupPlaceholder: 'Cita, familia, amigos que no se ponen de acuerdo...',
    notesLabel: 'Comentario opcional',
    notesPlaceholder: 'Evitar terror, menos de dos horas, sin subtitulos hoy...',
    loading: 'Eligiendo...',
    submit: 'Recomendar una pelicula',
    pick: 'La eleccion de hoy',
    whyRecommended: 'Por que esta recomendacion?',
    watchOn: (provider: string) => `Ver en ${provider}`,
    donationEyebrow: 'Apoyo',
    donationTitle: 'Invitame a un cafe',
    donationCopy:
      'Si Mind the Movie te ayudo a elegir pelicula, puedes apoyar el proyecto con una pequena donacion.',
    donationCta: 'Donar con Stripe',
    donationUnavailable:
      'Las donaciones estaran disponibles cuando se configure un enlace de pago de Stripe.',
    creatorName: 'Emilio Banqueri',
    creatorBio:
      'Soy Emilio Banqueri, un desarrollador que quiere que la tecnologia realmente apoye nuestro bienestar. Cree esto porque el scroll automatico y demasiadas opciones pueden afectar silenciosamente nuestra salud mental.',
    creatorPhotoAlt: 'Emilio Banqueri',
    errors: {
      recommendation: 'No se pudo obtener una recomendacion.',
      generic: 'Algo salio mal al elegir una pelicula.',
    },
  },
}

const languageFromPath = (pathname = window.location.pathname): Language => {
  const normalizedPath = pathname.toLowerCase().replace(/\/+$/, '') || '/'
  return normalizedPath === '/es' || normalizedPath.startsWith('/es/')
    ? 'es'
    : 'en'
}

const updateLanguageRoute = (
  newLanguage: Language,
  mode: 'push' | 'replace' = 'push',
) => {
  const nextPath =
    languageOptions.find((option) => option.id === newLanguage)?.path ?? '/'
  const nextUrl = `${nextPath}${window.location.search}${window.location.hash}`

  if (window.location.pathname === nextPath) {
    return
  }

  if (mode === 'replace') {
    window.history.replaceState(null, '', nextUrl)
    return
  }

  window.history.pushState(null, '', nextUrl)
}

function App() {
  const initialRouteLanguage = languageFromPath()
  const [selectedProviders, setSelectedProviders] = useState<ProviderId[]>([
    'netflix',
  ])
  const [language, setLanguage] = useState<Language>(initialRouteLanguage)
  const [region, setRegion] = useState('GB')
  const [locationStatus, setLocationStatus] =
    useState<LocationStatus>('detecting')
  const [mood, setMood] = useState('')
  const [groupContext, setGroupContext] = useState('')
  const [notes, setNotes] = useState('')
  const [allowExtraCosts, setAllowExtraCosts] = useState(false)
  const [recommendation, setRecommendation] = useState<Recommendation | null>(
    null,
  )
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [showCreatorPhoto, setShowCreatorPhoto] = useState(
    Boolean(creatorPhotoUrl),
  )
  const hasManualRegion = useRef(false)
  const hasManualLanguage = useRef(initialRouteLanguage === 'es')
  const t = translations[language]

  useEffect(() => {
    document.documentElement.lang = language
  }, [language])

  useEffect(() => {
    const syncLanguageFromRoute = () => {
      hasManualLanguage.current = true
      setLanguage(languageFromPath())
    }

    window.addEventListener('popstate', syncLanguageFromRoute)
    return () => {
      window.removeEventListener('popstate', syncLanguageFromRoute)
    }
  }, [])

  useEffect(() => {
    let isMounted = true

    const detectLocation = async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/api/location`)
        if (!response.ok) {
          throw new Error('Location lookup failed.')
        }

        const payload = (await response.json()) as LocationResponse
        const detectedRegion = payload.region.toUpperCase()
        if (!/^[A-Z]{2}$/.test(detectedRegion)) {
          throw new Error('Invalid location response.')
        }

        if (!isMounted) {
          return
        }

        if (hasManualRegion.current) {
          setLocationStatus('manual')
        } else {
          setRegion(detectedRegion)
          setLocationStatus(payload.detected ? 'detected' : 'default')
        }

        if (!hasManualLanguage.current) {
          const detectedLanguage = detectedRegion === 'ES' ? 'es' : 'en'
          setLanguage(detectedLanguage)
          updateLanguageRoute(detectedLanguage, 'replace')
        }
      } catch {
        if (!isMounted) {
          return
        }
        setLocationStatus('error')
      }
    }

    void detectLocation()

    return () => {
      isMounted = false
    }
  }, [])

  const canSubmit = useMemo(
    () =>
      selectedProviders.length > 0 &&
      mood.trim().length > 1 &&
      /^[A-Z]{2}$/.test(region) &&
      !isLoading,
    [isLoading, mood, region, selectedProviders.length],
  )

  const countryName = t.countries[region as keyof typeof t.countries] ?? region

  const locationMessage = useMemo(() => {
    if (locationStatus === 'detecting') {
      return t.regionHelp.detecting
    }
    return t.regionHelp[locationStatus](countryName)
  }, [countryName, locationStatus, t])

  const toggleProvider = (providerId: ProviderId) => {
    setSelectedProviders((currentProviders) =>
      currentProviders.includes(providerId)
        ? currentProviders.filter((currentProvider) => currentProvider !== providerId)
        : [...currentProviders, providerId],
    )
  }

  const selectRegion = (newRegion: string) => {
    hasManualRegion.current = true
    setRegion(newRegion)
    setLocationStatus('manual')
  }

  const selectLanguage = (
    event: MouseEvent<HTMLAnchorElement>,
    newLanguage: Language,
  ) => {
    if (
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    ) {
      return
    }

    event.preventDefault()
    hasManualLanguage.current = true
    setLanguage(newLanguage)
    updateLanguageRoute(newLanguage)
  }

  const submitRecommendationRequest = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setRecommendation(null)
    setIsLoading(true)

    try {
      const response = await fetch(`${apiBaseUrl}/api/recommendations`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          providers: selectedProviders,
          mood,
          region,
          language,
          allow_extra_costs: allowExtraCosts,
          group_context: groupContext || null,
          notes: notes || null,
        }),
      })

      if (!response.ok) {
        const payload = await response.json().catch(() => null)
        const detail = payload?.detail
        const message = Array.isArray(detail)
          ? detail.map((item: { msg?: string }) => item.msg).filter(Boolean).join(' ')
          : typeof detail === 'string'
            ? detail
            : null
        throw new Error(message ?? t.errors.recommendation)
      }

      setRecommendation(await response.json())
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : t.errors.generic,
      )
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="app-shell">
      <div className="top-controls">
        <nav className="language-switcher" aria-label={t.languageSwitcherLabel}>
          {languageOptions.map((option) => (
            <a
              aria-current={option.id === language ? 'page' : undefined}
              className={`language-option${
                option.id === language ? ' is-active' : ''
              }`}
              href={option.path}
              key={option.id}
              onClick={(event) => selectLanguage(event, option.id)}
            >
              <span aria-hidden="true" className="language-flag">
                {option.flag}
              </span>
              <span>{t.languages[option.id]}</span>
            </a>
          ))}
        </nav>

        <label className="location-control">
          <span className="location-label">{t.locationLabel}</span>
          <span className="location-message">{locationMessage}</span>
          <select
            aria-label={t.changeLocationLabel}
            onChange={(event) => selectRegion(event.target.value)}
            value={region}
          >
            {regionOptions.map((regionCode) => (
              <option key={regionCode} value={regionCode}>
                {t.countries[regionCode as keyof typeof t.countries] ?? regionCode}
              </option>
            ))}
          </select>
        </label>
      </div>

      <section className="hero">
        <img
          alt={t.appAlt}
          className="hero-logo"
          src={mindTheMovieLogo}
        />
        <h1>{t.title}</h1>
        <p className="hero-copy">
          {t.intro}
        </p>
      </section>

      <section className="panel">
        <form onSubmit={submitRecommendationRequest}>
          <fieldset>
            <legend>{t.providerLegend}</legend>
            <div className="provider-grid">
              {providers.map((provider) => (
                <label className="provider-card" key={provider.id}>
                  <input
                    checked={selectedProviders.includes(provider.id)}
                    onChange={() => toggleProvider(provider.id)}
                    type="checkbox"
                  />
                  <span>{provider.label}</span>
                </label>
              ))}
            </div>
          </fieldset>

          <label className="paid-option">
            <input
              checked={allowExtraCosts}
              onChange={(event) => setAllowExtraCosts(event.target.checked)}
              type="checkbox"
            />
            <span>
              <strong>{t.paidOption}</strong>
              <small>
                {t.paidOptionHelp}
              </small>
            </span>
          </label>

          <label className="field">
            <span>{t.moodLabel}</span>
            <input
              onChange={(event) => setMood(event.target.value)}
              placeholder={t.moodPlaceholder}
              required
              value={mood}
            />
          </label>

          <label className="field">
            <span>{t.groupLabel}</span>
            <input
              onChange={(event) => setGroupContext(event.target.value)}
              placeholder={t.groupPlaceholder}
              value={groupContext}
            />
          </label>

          <label className="field">
            <span>{t.notesLabel}</span>
            <textarea
              onChange={(event) => setNotes(event.target.value)}
              placeholder={t.notesPlaceholder}
              rows={4}
              value={notes}
            />
          </label>

          <button disabled={!canSubmit} type="submit">
            {isLoading ? t.loading : t.submit}
          </button>
        </form>

        {error ? <p className="message error">{error}</p> : null}

        {recommendation ? (
          <article className="recommendation">
            <p className="eyebrow">{t.pick}</p>
            <h2>{recommendation.movie_title}</h2>
            <p className="recommendation-summary">{recommendation.reason}</p>
            <section className="recommendation-why">
              <h3>{t.whyRecommended}</h3>
              <p>{recommendation.why_recommended}</p>
            </section>
            <a href={recommendation.watch_link} rel="noreferrer" target="_blank">
              {t.watchOn(recommendation.provider)}
            </a>
          </article>
        ) : null}
      </section>

      <section className="donation-section" aria-labelledby="donation-title">
        <div className="creator-card">
          {showCreatorPhoto ? (
            <img
              alt={t.creatorPhotoAlt}
              className="creator-photo"
              onError={() => setShowCreatorPhoto(false)}
              src={creatorPhotoUrl}
            />
          ) : null}
          <div className="creator-copy">
            <p className="eyebrow">{t.donationEyebrow}</p>
            <h2 id="donation-title">{t.donationTitle}</h2>
            <p className="creator-name">{t.creatorName}</p>
            <p>{t.creatorBio}</p>
            <p>{t.donationCopy}</p>
          </div>
        </div>
        <div className="donation-action">
          {donationUrl ? (
            <a href={donationUrl} rel="noreferrer" target="_blank">
              {t.donationCta}
            </a>
          ) : (
            <span className="donation-muted">{t.donationUnavailable}</span>
          )}
        </div>
      </section>
    </main>
  )
}

export default App
