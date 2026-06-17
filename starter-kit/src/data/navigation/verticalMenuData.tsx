// Type Imports
import type { VerticalMenuDataType } from '@/types/menuTypes'

const verticalMenuData = (): VerticalMenuDataType[] => [
  {
    label: 'Voice',
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
