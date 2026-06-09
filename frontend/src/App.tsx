import './App.css'
import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import mindTheMovieLogo from './assets/mind-the-movie.svg'

type ProviderId = 'netflix' | 'disney' | 'youtube' | 'hbo'

type Recommendation = {
  movie_title: string
  provider: string
  watch_link: string
  reason: string
}

const providers: Array<{ id: ProviderId; label: string }> = [
  { id: 'netflix', label: 'Netflix' },
  { id: 'disney', label: 'Disney+' },
  { id: 'youtube', label: 'YouTube' },
  { id: 'hbo', label: 'HBO / NOW' },
]

const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
).replace(/\/+$/, '')

function App() {
  const [selectedProviders, setSelectedProviders] = useState<ProviderId[]>([
    'netflix',
  ])
  const [mood, setMood] = useState('')
  const [groupContext, setGroupContext] = useState('')
  const [notes, setNotes] = useState('')
  const [recommendation, setRecommendation] = useState<Recommendation | null>(
    null,
  )
  const [error, setError] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const canSubmit = useMemo(
    () => selectedProviders.length > 0 && mood.trim().length > 1 && !isLoading,
    [isLoading, mood, selectedProviders.length],
  )

  const toggleProvider = (providerId: ProviderId) => {
    setSelectedProviders((currentProviders) =>
      currentProviders.includes(providerId)
        ? currentProviders.filter((currentProvider) => currentProvider !== providerId)
        : [...currentProviders, providerId],
    )
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
        throw new Error(message ?? 'Could not get a recommendation.')
      }

      setRecommendation(await response.json())
    } catch (caughtError) {
      setError(
        caughtError instanceof Error
          ? caughtError.message
          : 'Something went wrong while choosing a movie.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="app-shell">
      <section className="hero">
        <img
          alt="Mind the Movie"
          className="hero-logo"
          src={mindTheMovieLogo}
        />
        <h1>Stop scrolling. Pick one movie.</h1>
        <p className="hero-copy">
          Tell us which providers you can use and what everyone feels like
          watching. We will suggest one movie with a simple way to start it.
        </p>
      </section>

      <section className="panel">
        <form onSubmit={submitRecommendationRequest}>
          <fieldset>
            <legend>Which providers can you use?</legend>
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

          <label className="field">
            <span>What do you feel like watching?</span>
            <input
              onChange={(event) => setMood(event.target.value)}
              placeholder="Funny, tense thriller, comfort movie, visually stunning..."
              required
              value={mood}
            />
          </label>

          <label className="field">
            <span>Who is watching?</span>
            <input
              onChange={(event) => setGroupContext(event.target.value)}
              placeholder="Date night, family, friends who cannot agree..."
              value={groupContext}
            />
          </label>

          <label className="field">
            <span>Optional comment</span>
            <textarea
              onChange={(event) => setNotes(event.target.value)}
              placeholder="Avoid horror, under two hours, no subtitles tonight..."
              rows={4}
              value={notes}
            />
          </label>

          <button disabled={!canSubmit} type="submit">
            {isLoading ? 'Choosing...' : 'Recommend one movie'}
          </button>
        </form>

        {error ? <p className="message error">{error}</p> : null}

        {recommendation ? (
          <article className="recommendation">
            <p className="eyebrow">Tonight's pick</p>
            <h2>{recommendation.movie_title}</h2>
            <p>{recommendation.reason}</p>
            <a href={recommendation.watch_link} rel="noreferrer" target="_blank">
              Watch on {recommendation.provider}
            </a>
          </article>
        ) : null}
      </section>
    </main>
  )
}

export default App
