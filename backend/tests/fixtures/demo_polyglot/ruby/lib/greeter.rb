# Greets people by name.
class Greeter
  def hello(name)
    "hello #{name}"
  end

  # Builds a default greeter.
  def self.build
    new
  end
end
