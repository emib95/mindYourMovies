import './App.css'
import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import mindTheMovieLogo from './assets/mind-the-movie.svg'

type ProviderId = 'netflix' | 'disney' | 'prime' | 'youtube' | 'hbo'
type Language = 'en' | 'es'
type LocationStatus = 'detecting' | 'detected' | 'default' | 'error'

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

const translations = {
  en: {
    appAlt: 'Mind the Movie',
    title: 'Stop scrolling. Pick one movie.',
    intro:
      'Tell us which providers you can use and what everyone feels like watching. We will suggest one movie with a simple way to start it.',
    languageLabel: 'Language',
    regionLabel: 'Availability country',
    regionHelp: {
      detecting: 'Detecting your country from your IP address...',
      detected: (country: string) => `Using availability for ${country}.`,
      default: (country: string) =>
        `Using ${country} as a fallback. You can change it before asking.`,
      error: (country: string) =>
        `Could not detect your country, so ${country} is selected for now.`,
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
      'When unchecked, TMDb results exclude paid rent/buy options such as many YouTube movies.',
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
    errors: {
      recommendation: 'Could not get a recommendation.',
      generic: 'Something went wrong while choosing a movie.',
    },
  },
  es: {
    appAlt: 'Mind the Movie',
    title: 'Deja de buscar. Elige una pelicula.',
    intro:
      'Dinos que plataformas puedes usar y que les apetece ver. Te sugeriremos una pelicula con una forma sencilla de empezar.',
    languageLabel: 'Idioma',
    regionLabel: 'Pais de disponibilidad',
    regionHelp: {
      detecting: 'Detectando tu pais por tu direccion IP...',
      detected: (country: string) => `Usando la disponibilidad de ${country}.`,
      default: (country: string) =>
        `Usando ${country} como opcion inicial. Puedes cambiarlo antes de pedir una recomendacion.`,
      error: (country: string) =>
        `No pudimos detectar tu pais, asi que ${country} esta seleccionado por ahora.`,
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
      'Si no esta marcada, TMDb excluye opciones de alquiler/compra como muchas peliculas de YouTube.',
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
    errors: {
      recommendation: 'No se pudo obtener una recomendacion.',
      generic: 'Algo salio mal al elegir una pelicula.',
    },
  },
}

const browserLanguage = (): Language =>
  navigator.language.toLowerCase().startsWith('es') ? 'es' : 'en'

function App() {
  const [selectedProviders, setSelectedProviders] = useState<ProviderId[]>([
    'netflix',
  ])
  const [language, setLanguage] = useState<Language>(browserLanguage)
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
  const hasManualRegion = useRef(false)
  const t = translations[language]

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

        if (!hasManualRegion.current) {
          setRegion(detectedRegion)
        }
        setLocationStatus(payload.detected ? 'detected' : 'default')
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
    setLocationStatus('detected')
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
          <div className="locale-grid">
            <label className="field">
              <span>{t.languageLabel}</span>
              <select
                onChange={(event) => setLanguage(event.target.value as Language)}
                value={language}
              >
                <option value="en">{t.languages.en}</option>
                <option value="es">{t.languages.es}</option>
              </select>
            </label>

            <label className="field">
              <span>{t.regionLabel}</span>
              <select
                onChange={(event) => selectRegion(event.target.value)}
                value={region}
              >
                {regionOptions.map((regionCode) => (
                  <option key={regionCode} value={regionCode}>
                    {t.countries[regionCode as keyof typeof t.countries] ?? regionCode}
                  </option>
                ))}
              </select>
              <small className="field-help">{locationMessage}</small>
            </label>
          </div>

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
    </main>
  )
}

export default App
