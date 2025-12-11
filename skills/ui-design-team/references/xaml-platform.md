# XAML Platform Specialist

Implement designs in WPF, WinUI 3, and .NET MAUI using XAML and MVVM patterns.

## Framework Selection

| Framework | Target | Best For |
|-----------|--------|----------|
| **WPF** | Windows desktop | Mature apps, rich customization, enterprise |
| **WinUI 3** | Windows 10/11 | Modern Windows apps, Fluent Design |
| **.NET MAUI** | Cross-platform | iOS, Android, Windows, macOS from single codebase |

## Core XAML Concepts

### Resources & Styles
```xml
<ResourceDictionary>
  <!-- Color palette -->
  <Color x:Key="Primary500">#3B82F6</Color>
  <Color x:Key="Primary600">#2563EB</Color>
  
  <!-- Brushes (semantic) -->
  <SolidColorBrush x:Key="PrimaryBrush" Color="{StaticResource Primary500}"/>
  <SolidColorBrush x:Key="BackgroundBrush" Color="#F9FAFB"/>
  
  <!-- Spacing -->
  <Thickness x:Key="SpacingSm">8</Thickness>
  <Thickness x:Key="SpacingMd">16</Thickness>
  
  <!-- Typography -->
  <x:Double x:Key="FontSizeBase">14</x:Double>
  <FontWeight x:Key="FontWeightSemibold">SemiBold</FontWeight>
  
  <!-- Corners -->
  <CornerRadius x:Key="RadiusMd">8</CornerRadius>
</ResourceDictionary>
```

### Styles with Visual States
```xml
<Style x:Key="PrimaryButtonStyle" TargetType="Button">
  <Setter Property="Background" Value="{StaticResource PrimaryBrush}"/>
  <Setter Property="Foreground" Value="White"/>
  <Setter Property="Padding" Value="{StaticResource SpacingMd}"/>
  <Setter Property="FontWeight" Value="{StaticResource FontWeightSemibold}"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="Button">
        <Border x:Name="RootBorder"
                Background="{TemplateBinding Background}"
                CornerRadius="{StaticResource RadiusMd}"
                Padding="{TemplateBinding Padding}">
          <VisualStateManager.VisualStateGroups>
            <VisualStateGroup x:Name="CommonStates">
              <VisualState x:Name="Normal"/>
              <VisualState x:Name="PointerOver">
                <Storyboard>
                  <ColorAnimation Storyboard.TargetName="RootBorder"
                                  Storyboard.TargetProperty="(Border.Background).(SolidColorBrush.Color)"
                                  To="{StaticResource Primary600}" Duration="0:0:0.15"/>
                </Storyboard>
              </VisualState>
              <VisualState x:Name="Pressed">
                <Storyboard>
                  <ColorAnimation Storyboard.TargetName="RootBorder"
                                  Storyboard.TargetProperty="(Border.Background).(SolidColorBrush.Color)"
                                  To="{StaticResource Primary600}" Duration="0:0:0.05"/>
                </Storyboard>
              </VisualState>
              <VisualState x:Name="Disabled">
                <Storyboard>
                  <DoubleAnimation Storyboard.TargetName="RootBorder"
                                   Storyboard.TargetProperty="Opacity"
                                   To="0.5" Duration="0"/>
                </Storyboard>
              </VisualState>
            </VisualStateGroup>
            <VisualStateGroup x:Name="FocusStates">
              <VisualState x:Name="Focused">
                <Storyboard>
                  <ObjectAnimationUsingKeyFrames Storyboard.TargetName="FocusBorder"
                                                  Storyboard.TargetProperty="Visibility">
                    <DiscreteObjectKeyFrame KeyTime="0" Value="Visible"/>
                  </ObjectAnimationUsingKeyFrames>
                </Storyboard>
              </VisualState>
            </VisualStateGroup>
          </VisualStateManager.VisualStateGroups>
          
          <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
        </Border>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>
```

## Layout Panels

| Panel | Use Case |
|-------|----------|
| `Grid` | Complex layouts with rows/columns |
| `StackPanel` | Linear vertical/horizontal stacking |
| `DockPanel` | Edge docking (WPF) |
| `WrapPanel` | Flowing wrap layout |
| `UniformGrid` | Equal-sized cells |

```xml
<Grid>
  <Grid.RowDefinitions>
    <RowDefinition Height="Auto"/>
    <RowDefinition Height="*"/>
    <RowDefinition Height="Auto"/>
  </Grid.RowDefinitions>
  
  <Border Grid.Row="0"><!-- Header --></Border>
  <ScrollViewer Grid.Row="1"><!-- Content --></ScrollViewer>
  <Border Grid.Row="2"><!-- Footer --></Border>
</Grid>
```

## MVVM Pattern

```xml
<!-- View -->
<UserControl x:Class="App.Views.MyView"
             xmlns:vm="clr-namespace:App.ViewModels"
             d:DataContext="{d:DesignInstance Type=vm:MyViewModel}">
  
  <Button Content="{Binding ButtonText}"
          Command="{Binding ClickCommand}"
          IsEnabled="{Binding IsEnabled}"/>
</UserControl>
```

```csharp
// ViewModel (using CommunityToolkit.Mvvm)
public partial class MyViewModel : ObservableObject
{
    [ObservableProperty]
    private string _buttonText = "Click Me";
    
    [ObservableProperty]
    private bool _isEnabled = true;
    
    [RelayCommand]
    private void Click()
    {
        // Handle click
    }
}
```

## Accessibility

```xml
<!-- Automation properties -->
<Button AutomationProperties.Name="Submit form"
        AutomationProperties.HelpText="Saves your changes and closes the dialog">
  <SymbolIcon Symbol="Save"/>
</Button>

<!-- Keyboard -->
<Button IsTabStop="True" 
        TabIndex="1"
        AccessKey="S">
  _Save
</Button>
```

## Performance Tips
- **Virtualization**: Use `VirtualizingStackPanel` for lists
- **Compiled bindings**: `x:Bind` (WinUI/UWP) over `Binding`
- **Deferred loading**: `x:Load="False"` for conditional content
- **Freeze resources**: `PresentationOptions:Freeze="True"` (WPF)

## Component Template

```xml
<!--
  Component: [Name]
  Purpose: [Description]
  Accessibility: [Key features]
-->
<UserControl x:Class="Namespace.ComponentName"
             xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
             xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
             AutomationProperties.Name="[Accessible name]">
  
  <UserControl.Resources>
    <!-- Component-scoped resources -->
  </UserControl.Resources>
  
  <!-- Component content -->
</UserControl>
```

## Output Standards

1. Well-formed XAML (compiles without errors)
2. MVVM-compliant (no code-behind logic)
3. Design tokens as StaticResource/ThemeResource
4. All visual states implemented (Normal, PointerOver, Pressed, Disabled, Focused)
5. AutomationProperties for accessibility
6. Keyboard navigation support (IsTabStop, TabIndex, AccessKey)
