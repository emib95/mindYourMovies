const productionApiBaseUrl = 'https://api.mindyourmovies.com'
const localApiBaseUrl = 'http://localhost:8000'

export const apiBaseUrl = (
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? localApiBaseUrl : productionApiBaseUrl)
).replace(/\/+$/, '')

export const donationUrl = (
  import.meta.env.VITE_DONATION_URL ??
  'https://buy.stripe.com/28E5kD9Am5ku4DIavWfYY00'
).trim()

export const creatorPhotoUrl = (
  import.meta.env.VITE_CREATOR_PHOTO_URL ?? '/emilio-banqueri.jpg'
).trim()
