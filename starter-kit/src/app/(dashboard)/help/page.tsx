import { STUDIO_NAME } from '@configs/studioBranding'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Typography from '@mui/material/Typography'
import Box from '@mui/material/Box'
import Divider from '@mui/material/Divider'

const sections = [
  {
    title: '1. License and start',
    body: [
      'Double-click VoxCPM Studio.bat. Setup runs automatically in the log (no license needed for install).',
      'Before Open UI or Start Studio, click Enter license and paste your VCPM2 key.',
      'Copy Machine ID and contact the author on Telegram (t.me/rornpisith) if you need a key.',
      'To stop servers, run stop.bat in the project folder.'
    ]
  },
  {
    title: '2. Generate speech (Feature page)',
    body: [
      'Open Feature in the sidebar.',
      'Type your text in Target Text — any of the 30 supported languages works without a language tag.',
      'Choose Speaker (male, female, child, neutral) or leave Auto to match a saved voice profile.',
      'Pick a voice: Auto, None, a built-in voice, or a saved profile from your library.',
      'Optional: upload reference audio and prompt text for voice cloning, or add a style instruction.',
      'Adjust CFG, inference steps, normalize, and denoise if needed, then click Generate.',
      'Play the result, watch the live process log, and save the output to your voice library if you like it.'
    ]
  },
  {
    title: '3. Voice library',
    body: [
      'Saved voices appear in the library on the Feature page.',
      'Use a saved profile from the voice picker, or delete profiles you no longer need.',
      'When saving, set a name and gender so Auto speaker matching can find the right voice.'
    ]
  },
  {
    title: '4. Tips',
    body: [
      'First synthesis may take longer while the model loads on your GPU.',
      'For best speed, use an NVIDIA GPU with up-to-date drivers.',
      'If the UI cannot reach the API, check that the launcher shows servers running on ports 8000 and 3000.'
    ]
  }
]

export default function HelpPage() {
  return (
    <Box>
      <Typography variant='h4' sx={{ mb: 1, fontWeight: 'bold' }}>
        Help
      </Typography>
      <Typography variant='body1' color='text.secondary' sx={{ mb: 4 }}>
        Guide to using {STUDIO_NAME}
      </Typography>

      <Card elevation={3} sx={{ borderRadius: 3 }}>
        <CardContent sx={{ p: { xs: 3, md: 4 } }}>
          {sections.map((section, index) => (
            <Box key={section.title} sx={{ mb: index < sections.length - 1 ? 4 : 0 }}>
              <Typography variant='h6' sx={{ mb: 1.5, fontWeight: 600 }}>
                {section.title}
              </Typography>
              {section.body.map(line => (
                <Typography key={line} variant='body2' color='text.secondary' sx={{ mb: 1, lineHeight: 1.7 }}>
                  {line}
                </Typography>
              ))}
              {index < sections.length - 1 && <Divider sx={{ mt: 3 }} />}
            </Box>
          ))}
        </CardContent>
      </Card>
    </Box>
  )
}
