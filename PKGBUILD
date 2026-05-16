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
source=("${pkgname}-${pkgver}.tar.gz::https://github.com/Chloe-ko/launchy/archive/v${pkgver}.tar.gz")
sha256sums=('SKIP')

build() {
    cd "Launchy-${pkgver}"
    python -m build --wheel --no-isolation
}

package() {
    cd "Launchy-${pkgver}"
    python -m installer --destdir="$pkgdir" dist/*.whl

    install -Dm644 launchy/logo.svg "$pkgdir/usr/share/icons/hicolor/scalable/apps/launchy.svg"
    install -Dm644 launchy.desktop "$pkgdir/usr/share/applications/launchy.desktop"

    # Reference VDF (the Python launcher writes this itself, but useful for reference)
    install -Dm644 data/compatibilitytool.vdf "$pkgdir/usr/share/launchy/compatibilitytool.vdf"

    install -Dm644 LICENSE "$pkgdir/usr/share/licenses/${pkgname}/LICENSE"
}
