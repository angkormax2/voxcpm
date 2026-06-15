// Type Imports
import type { VerticalMenuDataType } from '@/types/menuTypes'

const verticalMenuData = (): VerticalMenuDataType[] => [
  {
    label: 'Feature',
    href: '/home',
    icon: 'ri-mic-line'
  },
  {
    label: 'Help',
    href: '/help',
    icon: 'ri-book-open-line'
  }
]

export default verticalMenuData
