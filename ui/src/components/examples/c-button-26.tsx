import { Button } from "@/components/ui/button"
import { PlayIcon } from "lucide-react"

export function Pattern() {
  return (
    <Button size="icon-lg" aria-label="Play">
      <PlayIcon aria-hidden="true" />
    </Button>
  )
}