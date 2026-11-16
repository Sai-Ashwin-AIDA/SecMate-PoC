import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { AssessmentSelect } from "./AssessmentSelect";

const options = [{ value: "a", label: "Alpha" }, { value: "b", label: "Beta", disabled: true }, { value: "g", label: "Gamma" }];

it("supports keyboard selection, skips disabled options and keeps focus on the combobox", async () => {
  const user = userEvent.setup(), onChange = vi.fn();
  render(<AssessmentSelect label="Test choice" value="a" options={options} onChange={onChange} />);
  const trigger = screen.getByRole("combobox", { name: "Test choice" });
  trigger.focus();
  await user.keyboard("{ArrowDown}{ArrowDown}{Enter}");
  expect(onChange).toHaveBeenCalledExactlyOnceWith("g");
  expect(trigger).toHaveFocus();
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});

it("supports search, Escape, outside dismissal and disabled choices without committing", async () => {
  const user = userEvent.setup(), onChange = vi.fn();
  render(<><AssessmentSelect label="Test choice" value="a" options={options} onChange={onChange} /><button>Outside</button></>);
  const trigger = screen.getByRole("combobox");
  await user.click(trigger);
  await user.click(screen.getByRole("option", { name: "Beta" }));
  expect(onChange).not.toHaveBeenCalled();
  await user.keyboard("g");
  expect(trigger.getAttribute("aria-activedescendant")).toBe(screen.getByRole("option", { name: "Gamma" }).id);
  await user.keyboard("{Escape}");
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: "Outside" }));
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
});

it("retains active identity on reorder and reconciles removed/disabled choices without committing", async () => {
  const user = userEvent.setup(), onChange = vi.fn();
  const view = render(<AssessmentSelect label="Choice" value="a" options={options} onChange={onChange} />);
  const trigger = screen.getByRole("combobox");
  await user.click(trigger);
  await user.keyboard("{ArrowDown}");
  const activeLabel = () => document.getElementById(trigger.getAttribute("aria-activedescendant") ?? "")?.textContent;
  expect(activeLabel()).toBe("Gamma");
  view.rerender(<AssessmentSelect label="Choice" value="a" options={[options[2], options[0]]} onChange={onChange} />);
  expect(activeLabel()).toBe("Gamma");
  view.rerender(<AssessmentSelect label="Choice" value="a" options={[options[0], { ...options[2], disabled: true }]} onChange={onChange} />);
  expect(activeLabel()).toBe("Alpha");
  view.rerender(<AssessmentSelect label="Choice" value="a" options={[{ value: "r", label: "Replacement" }]} onChange={onChange} />);
  expect(activeLabel()).toBe("Replacement");
  expect(onChange).not.toHaveBeenCalled();
  await user.keyboard("{Enter}");
  expect(onChange).toHaveBeenCalledExactlyOnceWith("r");
});

it("dismisses on all-disabled/empty options or external disable, and never reopens by itself", async () => {
  const user = userEvent.setup(), onChange = vi.fn();
  const view = render(<AssessmentSelect label="Choice" value="a" options={options} onChange={onChange} />);
  await user.click(screen.getByRole("combobox"));
  view.rerender(<AssessmentSelect label="Choice" value="a" options={options} onChange={onChange} disabled />);
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  view.rerender(<AssessmentSelect label="Choice" value="a" options={options} onChange={onChange} />);
  expect(screen.getByRole("combobox")).toHaveAttribute("aria-expanded", "false");
  await user.click(screen.getByRole("combobox"));
  view.rerender(<AssessmentSelect label="Choice" value="a" options={options.map(option => ({ ...option, disabled: true }))} onChange={onChange} />);
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  expect(screen.getByRole("combobox")).toBeDisabled();
  view.rerender(<AssessmentSelect label="Choice" value="a" options={[]} onChange={onChange} />);
  expect(screen.getByRole("combobox")).not.toHaveAttribute("aria-activedescendant");
  expect(onChange).not.toHaveBeenCalled();
});

it("supports Home/End from closed state and repeated-character typeahead", async () => {
  const user = userEvent.setup();
  render(<AssessmentSelect label="Choice" value="g" options={[...options, { value: "a2", label: "Another" }]} onChange={vi.fn()} />);
  const trigger = screen.getByRole("combobox");
  trigger.focus();
  const activeLabel = () => document.getElementById(trigger.getAttribute("aria-activedescendant") ?? "")?.textContent;
  await user.keyboard("{Home}");
  expect(activeLabel()).toBe("Alpha");
  await user.keyboard("{Escape}{End}");
  expect(activeLabel()).toBe("Another");
  await user.keyboard("a");
  expect(activeLabel()).toBe("Alpha");
  await user.keyboard("a");
  expect(activeLabel()).toBe("Another");
});

it("allows option scrolling but dismisses when the page or anchor's ancestor scrolls", async () => {
  const user = userEvent.setup();
  render(<div data-testid="scroll-parent"><AssessmentSelect label="Choice" value="a" options={options} onChange={vi.fn()} /></div>);
  const trigger = screen.getByRole("combobox");
  let top = 0;
  vi.spyOn(trigger, "getBoundingClientRect").mockImplementation(() => ({ top, bottom: top + 42, left: 0 } as DOMRect));
  await user.click(trigger);
  fireEvent.scroll(screen.getByRole("listbox"));
  expect(trigger).toHaveAttribute("aria-expanded", "true");
  top = 30;
  fireEvent.scroll(screen.getByTestId("scroll-parent"));
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  await user.click(trigger);
  top = 60;
  fireEvent.scroll(window);
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
});
