# Maintainer: Chloe <chloesviel@gmail.com>
pkgname=launchy
pkgver=0.1
pkgrel=1
pkgdesc="Configurable Steam compatibility tool launcher with per-game settings UI"
arch=('any')
url="https://github.com/Chloe-ko/launchy"
license=('GPL3')
depends=(
    'python>=3.11'
    'python-gobject'
    'gtk4'
    'libadwaita'
)
makedepends=(
    'python-build'
    'python-installer'
    'python-wheel'
    'python-setuptools'
)
install="${pkgname}.install"
source=("${pkgname}-${pkgver}.tar.gz::https://github.com/Chloe-ko/launchy/archive/v${pkgver}.tar.gz")
sha256sums=('SKIP')

build() {
    cd "${pkgname}-${pkgver}"
    python -m build --wheel --no-isolation
}

package() {
    cd "${pkgname}-${pkgver}"
    python -m installer --destdir="$pkgdir" dist/*.whl

    # Install the shell-based install helper
    install -Dm755 install.sh "$pkgdir/usr/share/launchy/install.sh"

    # Reference VDF (the Python launcher writes this itself, but useful for reference)
    install -Dm644 data/compatibilitytool.vdf "$pkgdir/usr/share/launchy/compatibilitytool.vdf"

    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/${pkgname}/LICENSE"
}
