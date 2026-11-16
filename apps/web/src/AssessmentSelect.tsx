import { useEffect, useId, useRef, useState } from "react";

export type AssessmentOption = { value: string; label: string; disabled?: boolean };

/** Bounded, always-downward menu rather than an OS-positioned native popup. */
export function AssessmentSelect({ label, value, options, onChange, disabled = false }: {
  label: string; value: string; options: AssessmentOption[];
  onChange: (value: string) => void; disabled?: boolean;
}) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [activeValue, setActiveValue] = useState<string | null>(null);
  const [height, setHeight] = useState(240);
  const search = useRef({ text: "", time: 0 });
  const selected = options.findIndex(option => option.value === value);
  const enabled = options.flatMap((option, index) => option.disabled ? [] : [index]);
  const activeMatch = options.findIndex(option => option.value === activeValue && !option.disabled);
  const active = activeMatch >= 0 ? activeMatch : selected >= 0 && !options[selected].disabled ? selected : enabled[0];
  const expanded = open && !disabled && enabled.length > 0;
  const activate = (index: number) => setActiveValue(options[index]?.value ?? null);
  const show = (position: "selected" | "first" | "last" = "selected") => {
    if (disabled || !enabled.length) return;
    // Make room below; direction never flips depending on the selected option.
    const button = trigger.current;
    if (button && window.innerHeight - button.getBoundingClientRect().bottom < 260) {
      button.scrollIntoView?.({ block: "center", behavior: "instant" });
    }
    const available = Math.max(0, window.innerHeight - (button?.getBoundingClientRect().bottom ?? 0) - 16);
    if (!available) return;
    setHeight(Math.min(240, available));
    activate(position === "last" ? enabled[enabled.length - 1] : position === "first" ? enabled[0] : selected >= 0 && !options[selected].disabled ? selected : enabled[0]);
    search.current = { text: "", time: 0 };
    setOpen(true);
  };
  const choose = (index: number) => {
    if (disabled || !options[index] || options[index].disabled) return;
    onChange(options[index].value);
    setOpen(false);
    trigger.current?.focus();
  };
  useEffect(() => {
    if (!open) return;
    if (!expanded) setOpen(false);
    else if (options[active]?.value !== activeValue) activate(active);
  }, [open, expanded, active, activeValue, options]);
  useEffect(() => {
    if (!expanded) return;
    const anchor = trigger.current?.getBoundingClientRect();
    const dismiss = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const resize = () => setOpen(false);
    const scroll = (event: Event) => {
      // Scrolling the options is expected; moving the anchor/page dismisses it.
      if (!(event.target instanceof Node) || !root.current?.contains(event.target)) {
        const current = trigger.current?.getBoundingClientRect();
        // scrollIntoView's queued opening event must not dismiss a menu whose
        // anchor is already at the measured position.
        if (!anchor || !current || Math.abs(current.top - anchor.top) > 1 || Math.abs(current.left - anchor.left) > 1) setOpen(false);
      }
    };
    document.addEventListener("pointerdown", dismiss);
    window.addEventListener("resize", resize);
    window.addEventListener("scroll", scroll, true);
    window.visualViewport?.addEventListener("resize", resize);
    window.visualViewport?.addEventListener("scroll", resize);
    return () => {
      document.removeEventListener("pointerdown", dismiss); window.removeEventListener("resize", resize);
      window.removeEventListener("scroll", scroll, true);
      window.visualViewport?.removeEventListener("resize", resize);
      window.visualViewport?.removeEventListener("scroll", resize);
    };
  }, [expanded]);
  useEffect(() => {
    if (!expanded) return;
    const option = document.getElementById(`${id}-option-${active}`), menu = option?.parentElement;
    if (option && menu) {
      if (option.offsetTop < menu.scrollTop) menu.scrollTop = option.offsetTop;
      else if (option.offsetTop + option.offsetHeight > menu.scrollTop + menu.clientHeight) menu.scrollTop = option.offsetTop + option.offsetHeight - menu.clientHeight;
    }
  }, [expanded, active, id]);
  return <div className="assessment-select" ref={root}>
    <span id={`${id}-label`} className="assessment-select-label">{label}</span>
    <button ref={trigger} className="assessment-select-trigger" type="button" role="combobox"
      aria-labelledby={`${id}-label`}
      aria-haspopup="listbox" aria-expanded={expanded} aria-controls={expanded ? `${id}-list` : undefined}
      aria-activedescendant={expanded ? `${id}-option-${active}` : undefined} disabled={disabled || !enabled.length}
      onClick={() => expanded ? setOpen(false) : show()}
      onBlur={event => { if (!root.current?.contains(event.relatedTarget as Node)) setOpen(false); }}
      onKeyDown={event => {
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          if (!expanded) { show(event.key === "End" ? "last" : event.key === "Home" ? "first" : "selected"); return; }
          const position = enabled.indexOf(active);
          activate(event.key === "Home" ? enabled[0] : event.key === "End" ? enabled[enabled.length - 1]
            : enabled[(position + (event.key === "ArrowDown" ? 1 : -1) + enabled.length) % enabled.length]);
        } else if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          if (expanded) choose(active); else show();
        } else if (event.key === "Escape") {
          event.preventDefault(); setOpen(false);
        } else if (event.key === "Tab") {
          setOpen(false);
        } else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
          event.preventDefault();
          if (!expanded) show();
          const now = Date.now();
          const term = (now - search.current.time > 700 ? "" : search.current.text) + event.key.toLowerCase();
          search.current = { text: term, time: now };
          const repeated = term.split("").every(character => character === term[0]);
          const prefix = repeated ? term[0] : term;
          const start = expanded && repeated ? enabled.indexOf(active) + 1 : 0;
          const match = Array.from({ length: enabled.length }, (_, i) => enabled[(start + i) % enabled.length])
            .find(index => options[index].label.toLowerCase().startsWith(prefix));
          if (match !== undefined) activate(match);
        }
      }}>
      <span id={`${id}-value`}>{options[selected]?.label ?? "Choose an option"}</span><span aria-hidden="true">⌄</span>
    </button>
    {expanded && <ul id={`${id}-list`} role="listbox" aria-label={label} className="assessment-select-menu" style={{ maxHeight: height }}>
      {options.map((option, index) => <li id={`${id}-option-${index}`} key={option.value} role="option"
        aria-selected={option.value === value} aria-disabled={option.disabled || undefined}
        className={active === index ? "active" : ""}
        onPointerDown={event => event.preventDefault()}
        onMouseMove={() => { if (!option.disabled) activate(index); }} onClick={() => choose(index)}>{option.label}</li>)}
    </ul>}
  </div>;
}
