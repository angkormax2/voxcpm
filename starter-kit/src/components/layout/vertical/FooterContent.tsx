'use client'

// Hook Imports
import useVerticalNav from '@menu/hooks/useVerticalNav'

// Component Imports
import StudioFooterContent from '@components/layout/shared/StudioFooterContent'

// Util Imports
import { verticalLayoutClasses } from '@layouts/utils/layoutClasses'

const FooterContent = () => {
  const { isBreakpointReached } = useVerticalNav()

  return (
    <StudioFooterContent
      className={verticalLayoutClasses.footerContent}
      hideLinksOnMobile
      isBreakpointReached={isBreakpointReached}
    />
  )
}

export default FooterContent
