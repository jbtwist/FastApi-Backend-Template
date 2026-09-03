import { createRef } from 'react';
import { TextInput } from 'react-native';

import { fireEvent, renderWithProviders, screen } from '@/test-utils';

import { PasswordField } from '../password-field';

describe('<PasswordField />', () => {
  it('renders the label and masks the input by default', () => {
    renderWithProviders(<PasswordField label="Password" value="hunter2" onChangeText={() => {}} />);

    expect(screen.getByText('Password')).toBeOnTheScreen();
    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(true);
  });

  it('exposes a show/hide toggle that starts on "show"', () => {
    renderWithProviders(<PasswordField label="Password" value="" onChangeText={() => {}} />);

    const toggle = screen.getByLabelText('Show password');
    expect(toggle).toBeOnTheScreen();
    expect(toggle.props.accessibilityRole).toBe('button');
    expect(screen.queryByLabelText('Hide password')).toBeNull();
  });

  it('reveals the value when the toggle is pressed and re-masks on a second press', () => {
    renderWithProviders(<PasswordField label="Password" value="s3cret" onChangeText={() => {}} />);

    fireEvent.press(screen.getByLabelText('Show password'));

    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(false);
    expect(screen.getByLabelText('Hide password')).toBeOnTheScreen();

    fireEvent.press(screen.getByLabelText('Hide password'));

    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(true);
    expect(screen.getByLabelText('Show password')).toBeOnTheScreen();
  });

  it('forwards an error to the underlying field as a live-region alert', () => {
    renderWithProviders(
      <PasswordField
        label="Password"
        value="x"
        onChangeText={() => {}}
        error="Password is too short"
      />,
    );

    expect(screen.getByRole('alert')).toHaveTextContent('Password is too short');
    expect(screen.getByLabelText('Password').props['aria-invalid']).toBe(true);
  });

  it('passes autoComplete / textContentType through and forwards its ref', () => {
    const ref = createRef<TextInput>();
    renderWithProviders(
      <PasswordField
        label="New password"
        value=""
        onChangeText={() => {}}
        autoComplete="new-password"
        textContentType="newPassword"
        ref={ref}
      />,
    );

    const input = screen.getByLabelText('New password');
    expect(input.props.autoComplete).toBe('new-password');
    expect(input.props.textContentType).toBe('newPassword');
    expect(ref.current).not.toBeNull();
  });

  it('calls onChangeText when the user types', () => {
    const onChangeText = jest.fn();
    renderWithProviders(<PasswordField label="Password" value="" onChangeText={onChangeText} />);

    fireEvent.changeText(screen.getByLabelText('Password'), 'letmein');
    expect(onChangeText).toHaveBeenCalledWith('letmein');
  });

  it('keeps the caller-supplied secureTextEntry:false intent from leaking the toggle state back', () => {
    // revealing then re-masking must land on masked regardless of prop churn
    const { rerender } = renderWithProviders(
      <PasswordField label="Password" value="a" onChangeText={() => {}} />,
    );
    fireEvent.press(screen.getByLabelText('Show password'));
    rerender(<PasswordField label="Password" value="ab" onChangeText={() => {}} />);
    expect(screen.getByLabelText('Password').props.secureTextEntry).toBe(false);
  });
});
