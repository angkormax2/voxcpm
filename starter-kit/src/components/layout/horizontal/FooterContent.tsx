'use client'

// Hook Imports
import useHorizontalNav from '@menu/hooks/useHorizontalNav'

// Component Imports
import StudioFooterContent from '@components/layout/shared/StudioFooterContent'

// Util Imports
import { horizontalLayoutClasses } from '@layouts/utils/layoutClasses'

const FooterContent = () => {
  const { isBreakpointReached } = useHorizontalNav()

  return (
    <StudioFooterContent
      className={horizontalLayoutClasses.footerContent}
      hideLinksOnMobile
      isBreakpointReached={isBreakpointReached}
    />
  )
}

export default FooterContent
