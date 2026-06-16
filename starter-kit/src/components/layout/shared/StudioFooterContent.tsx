'use client'

// Third-party Imports
import classnames from 'classnames'

// Config Imports
import { STUDIO_NAME } from '@configs/studioBranding'

type StudioFooterContentProps = {
  className: string
  hideLinksOnMobile?: boolean
  isBreakpointReached?: boolean
}

const StudioFooterContent = ({
  className,
  hideLinksOnMobile = false,
  isBreakpointReached = false
}: StudioFooterContentProps) => {
  return (
    <div className={classnames(className, 'flex items-center justify-between flex-wrap gap-4')}>
      <p className='m-0'>
        <span>{`© ${new Date().getFullYear()}, `}</span>
        <span>{STUDIO_NAME}</span>
      </p>
    </div>
  )
}

export default StudioFooterContent
