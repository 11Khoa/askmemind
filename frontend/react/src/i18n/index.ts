import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import { en } from './resources/en'

export const defaultLanguage = 'en'

void i18n
  .use(initReactI18next)
  .init({
    fallbackLng: defaultLanguage,
    lng: defaultLanguage,
    interpolation: {
      escapeValue: false,
    },
    resources: {
      en: {
        translation: en,
      },
    },
  })

export default i18n