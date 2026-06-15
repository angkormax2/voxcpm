'use client'

// Next Imports
import Link from 'next/link'

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
  const showLinks = !hideLinksOnMobile || !isBreakpointReached

  return (
    <div className={classnames(className, 'flex items-center justify-between flex-wrap gap-4')}>
      <p className='m-0'>
        <span>{`© ${new Date().getFullYear()}, `}</span>
        <span>{STUDIO_NAME}</span>
      </p>
      {showLinks && (
        <div className='flex items-center gap-4'>
          <Link href='/help' className='text-primary'>
            Help
          </Link>
          <Link href='https://t.me/rornpisith' target='_blank' rel='noopener noreferrer' className='text-primary'>
            Telegram
          </Link>
        </div>
      )}
    </div>
  )
}

export default StudioFooterContent
