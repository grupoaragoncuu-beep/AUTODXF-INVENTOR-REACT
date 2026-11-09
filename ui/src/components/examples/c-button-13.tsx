import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"

export function Pattern() {
  return (
    <Button disabled>
      <Spinner aria-hidden="true" />
      Please wait
    </Button>
  )
}