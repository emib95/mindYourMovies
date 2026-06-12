import './App.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, MouseEvent } from 'react'
import mindTheMovieLogo from './assets/mind-the-movie.svg'
import { apiBaseUrl, creatorPhotoUrl, donationUrl } from './config'
import { countryNameFor, regionCodes } from './countries'

type ProviderId = 'netflix' | 'disney' | 'prime' | 'youtube' | 'hbo'
type Language = 'en' | 'es'
type LocationStatus = 'detecting' | 'detected' | 'default' | 'error' | 'manual'

type Recommendation = {
  movie_title: string
  provider: string
  watch_link: string
  reason: string
  why_recommended: string
  tmdb_id: number | null
  region: string
  language: Language
}

type ExcludedRecommendation = {
  tmdbId: number | null
  title: string
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
    loading: 'Rolling...',
    loadingTitle: 'Spooling up the projector',
    loadingDetail:
      'Threading your mood through the reels to find one movie worth pressing play.',
    submit: 'Recommend one movie',
    pick: "Tonight's pick",
    whyRecommended: 'Why this recommendation?',
    watchOn: (provider: string) => `Watch on ${provider}`,
    differentRecommendation:
      "I've already watched this. Recommend a different movie.",
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
    title: 'Deja de buscar. Elige una película.',
    intro:
      'Dinos qué plataformas puedes usar y qué les apetece ver. Te sugeriremos una película con una forma sencilla de empezar.',
    languageLabel: 'Idioma',
    locationLabel: 'Ubicación detectada',
    changeLocationLabel: 'Cambiar país de disponibilidad',
    regionLabel: 'País de disponibilidad',
    regionHelp: {
      detecting: 'Detectando tu país por tu dirección IP...',
      detected: (country: string) =>
        `Ubicación detectada: ${country}. Puedes cambiarla aquí.`,
      default: (country: string) =>
        `Usando ${country} como opción inicial. Puedes cambiarla aquí.`,
      error: (country: string) =>
        `No pudimos detectar tu país, así que ${country} está seleccionado por ahora. Puedes cambiarlo aquí.`,
      manual: (country: string) =>
        `Usando la disponibilidad de ${country}. Puedes cambiarla aquí.`,
    },
    languages: {
      en: 'Inglés',
      es: 'Español',
    },
    providerLegend: '¿Qué plataformas puedes usar?',
    paidOption: 'Estoy dispuesto a pagar extra por alquileres o compras.',
    paidOptionHelp:
      'Si no está marcada, se excluyen opciones de alquiler/compra como muchas películas de YouTube.',
    moodLabel: '¿Qué te apetece ver?',
    moodPlaceholder:
      'Comedia, thriller tenso, película reconfortante, algo visual...',
    groupLabel: '¿Quién va a ver la película?',
    groupPlaceholder: 'Cita, familia, amigos que no se ponen de acuerdo...',
    notesLabel: 'Comentario opcional',
    notesPlaceholder: 'Evitar terror, menos de dos horas, sin subtítulos hoy...',
    loading: 'Rodando...',
    loadingTitle: 'Preparando el proyector',
    loadingDetail:
      'Pasando tu estado de ánimo por los carretes para encontrar una película que merezca darle al play.',
    submit: 'Recomendar una película',
    pick: 'La elección de hoy',
    whyRecommended: '¿Por qué esta recomendación?',
    watchOn: (provider: string) => `Ver en ${provider}`,
    differentRecommendation:
      'Ya he visto esta pelicula. Recomiendame una diferente.',
    donationEyebrow: 'Apoyo',
    donationTitle: 'Invítame a un café',
    donationCopy:
      'Si Mind the Movie te ayudó a elegir película, puedes apoyar el proyecto con una pequeña donación.',
    donationCta: 'Donar con Stripe',
    donationUnavailable:
      'Las donaciones estarán disponibles cuando se configure un enlace de pago de Stripe.',
    creatorName: 'Emilio Banqueri',
    creatorBio:
      'Soy Emilio Banqueri, un desarrollador que quiere que la tecnología realmente apoye nuestro bienestar. Creé esto porque el scroll automático y demasiadas opciones pueden afectar silenciosamente nuestra salud mental.',
    creatorPhotoAlt: 'Emilio Banqueri',
    errors: {
      recommendation: 'No se pudo obtener una recomendación.',
      generic: 'Algo salió mal al elegir una película.',
    },
  },
}

const languageFromPath = (pathname = window.location.pathname): Language => {
  const normalizedPath = pathname.toLowerCase().replace(/\/+$/, '') || '/'
  return normalizedPath === '/es' || normalizedPath.startsWith('/es/')
    ? 'es'
    : 'en'
}

const isUkRoute = (pathname = window.location.pathname): boolean => {
  const normalizedPath = pathname.toLowerCase().replace(/\/+$/, '') || '/'
  return normalizedPath === '/uk' || normalizedPath.startsWith('/uk/')
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

const appendExcludedRecommendation = (
  currentExclusions: ExcludedRecommendation[],
  recommendation: Recommendation,
): ExcludedRecommendation[] => {
  const nextExclusion = {
    tmdbId: recommendation.tmdb_id,
    title: recommendation.movie_title,
  }
  const exclusionKey = (excluded: ExcludedRecommendation) =>
    excluded.tmdbId
      ? `id:${excluded.tmdbId}`
      : `title:${excluded.title.trim().toLowerCase()}`
  const nextKey = exclusionKey(nextExclusion)

  return [
    ...currentExclusions.filter(
      (excluded) => exclusionKey(excluded) !== nextKey,
    ),
    nextExclusion,
  ].slice(-25)
}

function App() {
  const initialRouteLanguage = languageFromPath()
  const [isStaticUkRoute] = useState(() => isUkRoute())
  const [selectedProviders, setSelectedProviders] = useState<ProviderId[]>([
    'netflix',
  ])
  const [language, setLanguage] = useState<Language>(initialRouteLanguage)
  const [region, setRegion] = useState('GB')
  const [locationStatus, setLocationStatus] = useState<LocationStatus>(
    isStaticUkRoute ? 'manual' : 'detecting',
  )
  const [mood, setMood] = useState('')
  const [groupContext, setGroupContext] = useState('')
  const [notes, setNotes] = useState('')
  const [allowExtraCosts, setAllowExtraCosts] = useState(false)
  const [recommendation, setRecommendation] = useState<Recommendation | null>(
    null,
  )
  const [excludedRecommendations, setExcludedRecommendations] = useState<
    ExcludedRecommendation[]
  >([])
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [showCreatorPhoto, setShowCreatorPhoto] = useState(
    Boolean(creatorPhotoUrl),
  )
  const hasManualRegion = useRef(isStaticUkRoute)
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
    if (isStaticUkRoute) {
      return
    }

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
  }, [isStaticUkRoute])

  const canSubmit = useMemo(
    () =>
      selectedProviders.length > 0 &&
      mood.trim().length > 1 &&
      /^[A-Z]{2}$/.test(region) &&
      !isLoading,
    [isLoading, mood, region, selectedProviders.length],
  )

  const regionOptions = useMemo(() => {
    const options: Array<{ code: string; label: string }> = regionCodes.map((regionCode) => ({
      code: regionCode,
      label: countryNameFor(regionCode, language),
    }))

    if (
      /^[A-Z]{2}$/.test(region) &&
      !(regionCodes as readonly string[]).includes(region)
    ) {
      options.push({
        code: region,
        label: countryNameFor(region, language),
      })
    }

    return options.sort((firstOption, secondOption) =>
      firstOption.label.localeCompare(secondOption.label, language),
    )
  }, [language, region])

  const countryName = countryNameFor(region, language)

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

  const requestRecommendation = async (
    exclusions: ExcludedRecommendation[] = [],
  ) => {
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
          excluded_tmdb_ids: exclusions
            .map((excluded) => excluded.tmdbId)
            .filter((tmdbId): tmdbId is number => typeof tmdbId === 'number'),
          excluded_movie_titles: exclusions.map((excluded) => excluded.title),
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

      setRecommendation((await response.json()) as Recommendation)
      setExcludedRecommendations(exclusions)
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

  const submitRecommendationRequest = async (event: FormEvent) => {
    event.preventDefault()
    setExcludedRecommendations([])
    await requestRecommendation()
  }

  const requestDifferentRecommendation = async () => {
    if (!recommendation) {
      return
    }

    const nextExclusions = appendExcludedRecommendation(
      excludedRecommendations,
      recommendation,
    )
    await requestRecommendation(nextExclusions)
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
            {regionOptions.map((regionOption) => (
              <option key={regionOption.code} value={regionOption.code}>
                {regionOption.label}
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

          <button aria-busy={isLoading} disabled={!canSubmit} type="submit">
            {isLoading ? t.loading : t.submit}
          </button>
        </form>

        {error ? <p className="message error">{error}</p> : null}

        {isLoading ? (
          <section
            aria-live="polite"
            className="loading-recommendation"
            role="status"
          >
            <div aria-hidden="true" className="film-loader">
              <span className="film-reel film-reel-one" />
              <span className="film-reel film-reel-two" />
              <span className="film-strip" />
            </div>
            <div className="loading-copy">
              <p className="eyebrow">{t.loading}</p>
              <h2>{t.loadingTitle}</h2>
              <p>{t.loadingDetail}</p>
            </div>
          </section>
        ) : null}

        {recommendation ? (
          <article className="recommendation">
            <p className="eyebrow">{t.pick}</p>
            <h2>{recommendation.movie_title}</h2>
            <p className="recommendation-summary">{recommendation.reason}</p>
            <section className="recommendation-why">
              <h3>{t.whyRecommended}</h3>
              <p>{recommendation.why_recommended}</p>
            </section>
            <div className="recommendation-actions">
              <a href={recommendation.watch_link} rel="noreferrer" target="_blank">
                {t.watchOn(recommendation.provider)}
              </a>
              <button
                className="secondary-action"
                disabled={isLoading}
                onClick={requestDifferentRecommendation}
                type="button"
              >
                {isLoading ? t.loading : t.differentRecommendation}
              </button>
            </div>
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
