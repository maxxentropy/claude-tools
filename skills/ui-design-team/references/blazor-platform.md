# Blazor Platform Specialist

Build interactive web UIs using .NET and Blazor components.

## Hosting Models

| Model | Execution | Best For |
|-------|-----------|----------|
| **Blazor Server** | Server via SignalR | Internal apps, real-time, thin clients |
| **Blazor WebAssembly** | Client browser | Public apps, offline, CDN deployment |
| **Blazor United (.NET 8+)** | Per-component choice | Optimal per-page/component needs |
| **Blazor Hybrid** | Native shell + web UI | Desktop/mobile with web skills |

## Component Architecture

### Basic Component Structure
```razor
@* Component: [Name]
   Purpose: [Description]
   
   Parameters:
   - Label (string): Button text [Required]
   - OnClick (EventCallback): Click handler [Optional]
   
   Accessibility: Focusable, keyboard-operable
*@

@namespace MyApp.Components

<button class="btn @CssClass"
        type="button"
        disabled="@Disabled"
        aria-label="@AriaLabel"
        @onclick="HandleClick"
        @attributes="AdditionalAttributes">
    @Label
</button>

@code {
    [Parameter, EditorRequired]
    public string Label { get; set; } = string.Empty;
    
    [Parameter]
    public string? CssClass { get; set; }
    
    [Parameter]
    public string? AriaLabel { get; set; }
    
    [Parameter]
    public bool Disabled { get; set; }
    
    [Parameter]
    public EventCallback<MouseEventArgs> OnClick { get; set; }
    
    [Parameter(CaptureUnmatchedValues = true)]
    public Dictionary<string, object>? AdditionalAttributes { get; set; }
    
    private async Task HandleClick(MouseEventArgs e)
    {
        if (!Disabled)
        {
            await OnClick.InvokeAsync(e);
        }
    }
}
```

### Component Communication
- **Parameters**: Parent → Child
- **EventCallback**: Child → Parent
- **CascadingValue**: Ancestor → All descendants
- **State containers**: Shared state via DI services

## CSS Isolation (Scoped Styles)

**Component.razor.css** (co-located):
```css
/* Scoped to this component only */
.btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--spacing-xs);
    padding: var(--spacing-sm) var(--spacing-md);
    min-height: 44px;
    font-weight: 600;
    border: none;
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: background-color 150ms ease;
}

.btn:hover:not(:disabled) {
    background-color: var(--primary-600);
}

.btn:focus-visible {
    outline: 2px solid var(--primary-500);
    outline-offset: 2px;
}

.btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

/* Child elements (::deep required) */
::deep .btn__icon {
    width: 1em;
    height: 1em;
}
```

## Design Tokens in Blazor

**wwwroot/css/tokens.css**:
```css
:root {
    /* Colors */
    --primary-500: #3b82f6;
    --primary-600: #2563eb;
    --neutral-50: #f9fafb;
    --neutral-900: #111827;
    
    /* Semantic */
    --color-background: var(--neutral-50);
    --color-surface: white;
    --color-text-primary: var(--neutral-900);
    
    /* Spacing */
    --spacing-xs: 0.25rem;
    --spacing-sm: 0.5rem;
    --spacing-md: 1rem;
    --spacing-lg: 1.5rem;
    
    /* Typography */
    --font-size-base: 1rem;
    
    /* Borders */
    --radius-md: 0.5rem;
}

@media (prefers-color-scheme: dark) {
    :root {
        --color-background: var(--neutral-900);
        --color-surface: var(--neutral-800);
        --color-text-primary: var(--neutral-50);
    }
}
```

## Forms & Validation

```razor
<EditForm Model="@model" OnValidSubmit="HandleSubmit">
    <DataAnnotationsValidator />
    
    <div class="form-group">
        <label for="email">Email</label>
        <InputText id="email" 
                   @bind-Value="model.Email" 
                   class="form-input"
                   aria-describedby="email-error" />
        <ValidationMessage For="@(() => model.Email)" id="email-error" />
    </div>
    
    <button type="submit" class="btn btn--primary">Submit</button>
</EditForm>
```

## JavaScript Interop

```csharp
// Inject IJSRuntime
@inject IJSRuntime JS

// Call JS function
await JS.InvokeVoidAsync("localStorage.setItem", "key", "value");
var result = await JS.InvokeAsync<string>("localStorage.getItem", "key");

// Focus management
private ElementReference inputRef;
await inputRef.FocusAsync();
```

## Performance Optimization

- **ShouldRender()**: Override to prevent unnecessary renders
- **@key directive**: Help diff algorithm with lists
- **Virtualize component**: For large lists
- **Lazy loading**: `[assembly: AssemblyLazy]` for deferred assembly load
- **StateHasChanged()**: Call sparingly, only when needed

```razor
<Virtualize Items="@largeList" Context="item">
    <ItemContent>
        <div @key="item.Id">@item.Name</div>
    </ItemContent>
    <Placeholder>
        <div class="skeleton">Loading...</div>
    </Placeholder>
</Virtualize>
```

## Accessibility

```razor
<!-- ARIA attributes -->
<div role="alert" aria-live="polite">@StatusMessage</div>

<!-- Focus management -->
<input @ref="inputRef" aria-label="Search" />

@code {
    private ElementReference inputRef;
    
    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            await inputRef.FocusAsync();
        }
    }
}
```

## Output Standards

1. Clean component separation (presentational vs container)
2. CSS isolation for component styles
3. Design tokens as CSS custom properties
4. Full accessibility (ARIA, focus management, keyboard)
5. All states implemented (default, hover, focus, active, disabled)
6. EventCallback for child-to-parent communication
7. EditorRequired for mandatory parameters
8. XML documentation comments for public API
